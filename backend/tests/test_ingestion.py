from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.ingestion.service import ingest, reconcile_day
from app.models import DailyReferencePrice, QuoteSnapshot
from app.providers.csv_provider import HEADERS, parse_csv, read_csv

SAMPLE = Path(__file__).parents[2] / "sample-data" / "quotes.sample.csv"


def test_import_idempotent_and_daily_reference(db, settings):
    observations = parse_csv(SAMPLE.read_bytes())
    assert ingest(db, observations, settings) == {"inserted": 6, "duplicates": 0, "quarantined": 0}
    assert ingest(db, observations, settings)["duplicates"] == 6
    assert reconcile_day(db, date(2026, 11, 4), settings) == 1
    row = db.scalar(select(DailyReferencePrice))
    assert row.spot_snapshot_id is not None and row.fx_snapshot_id is not None
    assert reconcile_day(db, date(2026, 11, 6), settings) == 0


def test_sample_forbidden_in_production(db):
    settings = Settings(app_env="production", database_url="postgresql+psycopg://localhost/test")
    with pytest.raises(ValueError, match="SAMPLE"):
        ingest(db, parse_csv(SAMPLE.read_bytes()), settings)


def test_manual_requires_data_rights(db, settings):
    data = SAMPLE.read_bytes().replace(b",sample", b",manual")
    with pytest.raises(ValueError, match="quyền"):
        ingest(db, parse_csv(data), settings)
    assert ingest(db, parse_csv(data), settings, rights_confirmed=True)["inserted"] == 6


def test_quarantine_and_conflicting_duplicate(db, settings):
    observations = parse_csv(SAMPLE.read_bytes())
    ingest(db, observations, settings)
    original = next(o for o in observations if o.kind == "gold")
    changed = original.model_copy(
        update={
            "provider_timestamp": datetime(2026, 11, 6, 11, tzinfo=UTC),
            "ask": Decimal("300000000"),
            "raw_payload_hash": "a" * 64,
        }
    )
    assert ingest(db, [changed], settings, now=datetime(2026, 11, 7, tzinfo=UTC))["quarantined"] == 1
    assert reconcile_day(db, date(2026, 11, 6), settings) == 0
    with pytest.raises(ValueError, match="Conflicting"):
        ingest(db, [original.model_copy(update={"raw_payload_hash": "b" * 64})], settings)


def test_timezone_boundary_and_cutoff(db, settings):
    obs = parse_csv(SAMPLE.read_bytes())[0]
    # 17:30 UTC = next day 00:30 VN. Outside the closing window, never carried forward.
    obs = obs.model_copy(update={"provider_timestamp": datetime(2026, 11, 5, 17, 30, tzinfo=UTC)})
    ingest(db, [obs], settings)
    model = {"gold": QuoteSnapshot}.get(obs.kind)
    if model:
        assert db.scalar(select(model)).business_date == date(2026, 11, 6)
    assert reconcile_day(db, date(2026, 11, 5), settings) == 0
    assert reconcile_day(db, date(2026, 11, 6), settings) == 0


@pytest.mark.parametrize("bad", [b"NaN", b"Infinity", b"1e8", b"=cmd()", b"-1"])
def test_csv_rejects_bad_numeric(bad):
    with pytest.raises(ValueError):
        parse_csv(SAMPLE.read_bytes().replace(b"140000000", bad))


def test_csv_schema_size_and_path(tmp_path):
    with pytest.raises(ValueError):
        parse_csv(b"bad,header\n1,2\n")
    with pytest.raises(ValueError):
        parse_csv(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        read_csv(SAMPLE, tmp_path)
    assert len(HEADERS) == 9


def test_snapshot_immutable_and_no_demo_seed(db, settings):
    assert db.scalar(select(func.count()).select_from(QuoteSnapshot)) == 0
    ingest(db, parse_csv(SAMPLE.read_bytes()), settings)
    quote = db.scalar(select(QuoteSnapshot))
    quote.ask = Decimal("150000000")
    with pytest.raises(ValueError, match="append-only"):
        db.flush()
