"""Integration suite against a dedicated disposable database, never production."""

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.config import Settings, get_settings
from app.ingestion.service import ingest, reconcile_day
from app.models import DailyReferencePrice, QuoteSnapshot
from app.providers.csv_provider import parse_csv

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_engine(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL chưa cấu hình; không thay thế PostgreSQL bằng SQLite")
    if not make_url(url).database.startswith("gold_test"):
        pytest.fail("Chỉ dùng database có tên bắt đầu gold_test")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE daily_reference_prices, quote_snapshots, spot_snapshots, fx_snapshots, ingestion_runs, gold_products, data_sources RESTART IDENTITY CASCADE"
            )
        )
    yield engine, cfg
    engine.dispose()
    get_settings.cache_clear()


def test_pg_numeric_constraints_ingestion_and_append_only(pg_engine):
    engine, cfg = pg_engine
    settings = Settings(app_env="test", database_url=str(engine.url))
    with Session(engine) as db:
        seed_catalog(db)
        rows = parse_csv((Path(__file__).parents[2] / "sample-data/quotes.sample.csv").read_bytes())
        assert ingest(db, rows, settings)["inserted"] == 6
        assert ingest(db, rows, settings)["duplicates"] == 6
        reconcile_day(db, date(2026, 11, 4), settings)
        db.commit()
        assert db.scalar(select(QuoteSnapshot)).ask.as_tuple().exponent == -8
        assert db.scalar(select(DailyReferencePrice)).spot_snapshot_id is not None
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("UPDATE quote_snapshots SET ask = 1"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO gold_products(id,provider_id,product_code,name,location,purity,currency,unit,created_at) VALUES ('bad','sjc','bad','bad','HCM',2,'VND','VND/luong',now())"
            )
        )
    command.check(cfg)
    command.downgrade(cfg, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(cfg, "head")


def test_pg_readonly_role(pg_engine):
    engine, _ = pg_engine
    with engine.begin() as connection:
        connection.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gold_test_reader') THEN CREATE ROLE gold_test_reader NOLOGIN; END IF; END $$"
            )
        )
        connection.execute(text("GRANT USAGE ON SCHEMA public TO gold_test_reader"))
        connection.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO gold_test_reader"))
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE gold_test_reader"))
        assert connection.execute(text("SELECT COUNT(*) FROM quote_snapshots")).scalar() == 0
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE gold_test_reader"))
        connection.execute(text("DELETE FROM data_sources"))


def test_pg_dump_restore(pg_engine, tmp_path):
    engine, _ = pg_engine
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        pytest.skip("Cần PostgreSQL client tools cho test restore")
    url = engine.url
    environment = dict(
        os.environ,
        PGHOST=url.host or "127.0.0.1",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "postgres",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database,
    )
    with Session(engine) as db:
        seed_catalog(db)
        db.commit()
    dump = tmp_path / "test.dump"
    subprocess.run(
        [pg_dump, "--format=custom", "--no-owner", "--no-acl", "--file", str(dump)],
        env=environment,
        check=True,
        capture_output=True,
    )  # noqa: S603
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    subprocess.run(
        [pg_restore, "--no-owner", "--no-acl", "--exit-on-error", "--dbname", url.database, str(dump)],
        env=environment,
        check=True,
        capture_output=True,
    )  # noqa: S603
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM gold_products")).scalar() == 4
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "b8e3ab201001"
