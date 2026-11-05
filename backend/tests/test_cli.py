import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


def test_real_admin_cli_import_duplicate_and_unavailable_job(tmp_path):
    backend = Path(__file__).parents[1]
    root = backend.parent
    environment = dict(os.environ, APP_ENV="test", DATABASE_URL=f"sqlite:///{tmp_path / 'cli.db'}")

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", *args], cwd=backend, env=environment, capture_output=True, text=True
        )

    assert run("alembic", "upgrade", "head").returncode == 0
    assert run("app.jobs.catalog").returncode == 0
    arguments = (
        "app.jobs.import_csv",
        str(root / "sample-data/quotes.sample.csv"),
        "--import-root",
        str(root / "sample-data"),
    )
    first = run(*arguments)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["inserted"] == 6
    second = run(*arguments)
    assert second.returncode == 0
    assert json.loads(second.stdout)["duplicates"] == 6
    collector = run("app.jobs.collect_daily")
    assert collector.returncode == 2
    assert all(json.loads(line)["status"] == "source_unavailable" for line in collector.stdout.splitlines())
    engine = create_engine(environment["DATABASE_URL"])
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT SUM(inserted) FROM ingestion_runs WHERE status='success'")
            ).scalar()
            == 6
        )
        assert (
            connection.execute(
                text("SELECT SUM(duplicates) FROM ingestion_runs WHERE status='success'")
            ).scalar()
            == 6
        )
        assert connection.execute(text("SELECT COUNT(*) FROM daily_reference_prices")).scalar() == 2
    engine.dispose()
