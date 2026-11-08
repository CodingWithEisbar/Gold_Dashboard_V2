from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.ingestion.service import reconcile_day
from app.jobs.collect_daily import collect_source, run_collection
from app.models import DailyReferencePrice, DataSource, IngestionRun, QuoteSnapshot
from app.providers.btmh import PRODUCT_ID, BtmhGoldProvider, parse_btmh
from app.providers.safe_http import SourceUnavailable

FIXTURE = Path(__file__).parent / "fixtures/btmh.sample.html"
NOW = datetime(2026, 11, 5, 11, tzinfo=UTC)


def parse(payload=None, **kwargs):
    return parse_btmh(payload if payload is not None else FIXTURE.read_bytes(), now=NOW, **kwargs)


def licensed(db):
    db.get(DataSource, "btmh").license_status = "licensed"
    db.commit()


def test_only_verified_product_decimal_units_and_source_time():
    rows = parse()
    assert len(rows) == 1
    obs = rows[0]
    assert obs.product_id == PRODUCT_ID and obs.provider_id == "btmh"
    assert obs.bid == Decimal("137000000") and obs.ask == Decimal("141000000")
    assert obs.unit == "VND/luong" and obs.reference_type == "official"
    assert obs.provider_timestamp.isoformat() == "2026-11-05T17:55:00+07:00"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Đơn giá (nghìn VNĐ)", "Đơn giá (VNĐ)"),
        ("Đơn vị tính (ĐVT): chỉ", "Đơn vị tính (ĐVT): lượng"),
        ("<div>Mua vào</div><div>Bán ra</div>", "<div>Bán ra</div><div>Mua vào</div>"),
        ("Kim Gia Bảo 24K", "Kim Gia Bảo mới 24K"),
        ("<span>99.99</span>", "<span>99.9</span>"),
        ("<span>14.100</span>", "<span></span>"),
        ("<span>14.100</span>", "<span>13.000</span>"),
        ("<span>14.100</span>", "<span>14.10</span>"),
        ("<span>14.100</span>", "<span>1e4</span>"),
        ("<span>14.100</span>", "<span>NaN</span>"),
        ("<span>14.100</span>", "<span>+14.100</span>"),
        ("<span>14.100</span>", "<span>14,100</span>"),
        ("2026-11-05 17:55:00.0", "05/11/2026"),
        ("2026-11-05 17:55:00.0", "2026-02-31 17:55:00.0"),
        ('role="row"', 'role="listitem"'),
    ],
)
def test_fail_closed_on_schema_numeric_and_unit_changes(old, new):
    with pytest.raises(SourceUnavailable, match="provider_schema_changed"):
        parse(FIXTURE.read_text(encoding="utf-8").replace(old, new).encode())


def test_ambiguous_tables_malformed_html_and_limits():
    raw = FIXTURE.read_bytes()
    section = raw[
        raw.index(b'<div id="gold_price_table-49">') : raw.index(b'<div id="gold_price_table-889">')
    ]
    for bad in (
        raw + section,
        raw.replace(b"</h2>", b"</h3>"),
        b"x" * (2 * 1024 * 1024 + 1),
        b"<div>" * 82,
        b"\xff",
        raw.replace(b"<span>14.100</span>", b'<span id="a" id="b">14.100</span>'),
    ):
        with pytest.raises(SourceUnavailable, match="schema_changed"):
            parse(bad)


def test_stale_and_future_timestamps_are_not_relabelled():
    raw = FIXTURE.read_bytes()
    with pytest.raises(SourceUnavailable, match="data_stale"):
        parse(raw.replace(b"2026-11-05 17:55", b"2026-11-03 17:55"))
    with pytest.raises(SourceUnavailable, match="timestamp_in_future"):
        parse(raw.replace(b"2026-11-05 17:55", b"2026-11-06 17:55"))


def test_unrelated_page_changes_do_not_change_quote_identity():
    raw = FIXTURE.read_bytes()
    original = parse(raw)[0]
    for modified in (
        raw.replace(b"Unrelated content", b"Different news content"),
        raw.replace(b"14.600", b"14.800"),
        raw.replace(b"-200.000", b"-100.000"),
    ):
        assert parse(modified)[0].raw_payload_hash == original.raw_payload_hash
    changed = parse(raw.replace(b"14.100", b"14.200"))[0]
    assert changed.raw_payload_hash != original.raw_payload_hash


@pytest.mark.parametrize(
    ("flags", "code"),
    [
        ({}, "source_disabled"),
        ({"btmh_enabled": True}, "data_rights_not_confirmed"),
        ({"btmh_enabled": True, "btmh_license_confirmed": True}, "units_or_timezone_not_confirmed"),
    ],
)
def test_flags_block_all_http_before_fetch(monkeypatch, flags, code):
    def unexpected(*args):
        pytest.fail("Unapproved source must never make HTTP requests")

    monkeypatch.setattr("app.providers.btmh.fetch_btmh", unexpected)
    with pytest.raises(SourceUnavailable, match=code):
        BtmhGoldProvider(Settings(app_env="test", **flags)).fetch()


def test_job_catalog_rights_gate_before_provider(db, settings, monkeypatch):
    monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: pytest.fail("rights gate bypassed"))
    report = collect_source(db, "btmh", settings, now=NOW)
    assert report["error_code"] == "license_not_approved_in_catalog"
    assert db.scalar(select(IngestionRun)).status == "source_unavailable"
    assert db.scalar(select(func.count()).select_from(QuoteSnapshot)) == 0


def test_job_idempotency_cooldown_provenance_and_conflict(db, settings, monkeypatch):
    licensed(db)
    calls = []

    def fetch(self):
        calls.append(True)
        return parse()

    monkeypatch.setattr(BtmhGoldProvider, "fetch", fetch)
    first = collect_source(db, "btmh", settings, now=NOW)
    assert first["status"] == "success" and first["inserted"] == 1
    assert collect_source(db, "btmh", settings, now=NOW + timedelta(minutes=5))["status"] == "skipped"
    second = collect_source(db, "btmh", settings, now=NOW + timedelta(minutes=30))
    assert second["duplicates"] == 1 and second["inserted"] == 0 and len(calls) == 2
    quote = db.scalar(select(QuoteSnapshot))
    assert quote.source_url == "https://baotinmanhhai.vn/bang-gia-vang"
    assert quote.business_date == date(2026, 11, 5) and quote.provider_timestamp.hour == 10
    assert db.scalar(select(DailyReferencePrice)).product_id == PRODUCT_ID
    monkeypatch.setattr(
        BtmhGoldProvider, "fetch", lambda self: parse(FIXTURE.read_bytes().replace(b"14.100", b"14.200"))
    )
    conflict = collect_source(db, "btmh", settings, now=NOW + timedelta(hours=1))
    assert (
        conflict["status"] == "source_unavailable" and conflict["error_code"] == "quality_validation_failed"
    )
    assert db.scalar(select(QuoteSnapshot)).ask == Decimal("141000000")
    assert db.get(DataSource, "btmh").last_error_code == "quality_validation_failed"


def test_after_cutoff_is_saved_without_daily_reference(db, settings, monkeypatch):
    licensed(db)
    later = NOW + timedelta(hours=1)
    rows = parse_btmh(FIXTURE.read_bytes().replace(b"17:55:00.0", b"18:43:00.0"), now=later)
    monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: rows)
    assert collect_source(db, "btmh", settings, now=later)["inserted"] == 1
    assert reconcile_day(db, date(2026, 11, 5), settings) == 0
    assert db.scalar(select(func.count()).select_from(DailyReferencePrice)) == 0


def test_job_quarantine_and_single_source_exit_status(db, settings, monkeypatch):
    licensed(db)
    monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: parse())
    assert collect_source(db, "btmh", settings, now=NOW)["status"] == "success"
    next_day = NOW + timedelta(days=1)
    rows = parse_btmh(
        FIXTURE.read_bytes().replace(b"2026-11-05", b"2026-11-06").replace(b"14.100", b"30.000"), now=next_day
    )
    monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: rows)
    result = collect_source(db, "btmh", settings, now=next_day)
    assert result["status"] == "quarantined" and result["quarantined"] == 1
    assert db.get(DataSource, "btmh").last_error_code == "price_jump_requires_review"
    assert reconcile_day(db, date(2026, 11, 6), settings) == 0
    db.query(IngestionRun).delete()
    db.commit()
    results, code = run_collection(db, settings, "btmh")
    assert len(results) == 1 and results[0]["provider_id"] == "btmh" and code == 2


def test_source_failure_is_logged_without_payload_or_secret(db, settings, monkeypatch):
    licensed(db)

    def fetch(self):
        raise SourceUnavailable("provider_schema_changed")

    monkeypatch.setattr(BtmhGoldProvider, "fetch", fetch)
    results, code = run_collection(db, settings, "btmh")
    assert code == 2 and results[0]["error_code"] == "provider_schema_changed"
    assert db.get(DataSource, "btmh").last_success_at is None


def test_single_source_success_is_independent_of_other_missing_sources(db, settings, monkeypatch):
    licensed(db)
    monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: parse())
    reports, code = run_collection(db, settings, "btmh")
    assert code == 0 and [report["provider_id"] for report in reports] == ["btmh"]
    assert reports[0]["status"] == "success"
    reports, code = run_collection(db, settings)
    assert code == 2  # Metals.Dev has not been approved; full synchronization must stay incomplete.
    assert any(report.get("action") == "import_csv" for report in reports)


def test_long_retry_after_survives_new_sessions(db, settings, monkeypatch):
    from sqlalchemy.orm import Session

    licensed(db)
    calls = []

    def rate_limited(self):
        calls.append(True)
        raise SourceUnavailable("retry_after_exceeds_budget", retry_after_seconds=3600)

    monkeypatch.setattr(BtmhGoldProvider, "fetch", rate_limited)
    first = collect_source(db, "btmh", settings, now=NOW)
    assert first["status"] == "source_unavailable"
    assert db.get(DataSource, "btmh").next_poll_after == NOW + timedelta(hours=1)
    with Session(bind=db.bind) as restarted:
        skipped = collect_source(restarted, "btmh", settings, now=NOW + timedelta(minutes=30))
        assert skipped["reason"] == "provider_retry_after_active" and len(calls) == 1
        monkeypatch.setattr(BtmhGoldProvider, "fetch", lambda self: parse())
        assert (
            collect_source(restarted, "btmh", settings, now=NOW + timedelta(hours=1))["status"] == "success"
        )
        assert restarted.get(DataSource, "btmh").next_poll_after is None
