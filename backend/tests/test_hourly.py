from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ingestion.service import ingest
from app.jobs.collect_daily import collect_source
from app.models import DataSource, FuturesSnapshot, QuoteSnapshot, SpotSnapshot
from app.providers.csv_provider import HEADERS, parse_csv
from app.providers.doji import DojiGoldProvider, parse_doji
from app.providers.safe_http import SourceUnavailable
from app.repositories.prices import hourly_history

NOW = datetime(2026, 11, 5, 10, 55, tzinfo=UTC)
TABLE = """BẢNG GIÁ BẠC DOJI
Đơn vị: Nghìn VND/lượng
BẢNG GIÁ VÀNG DOJI
Cập nhật 17:42 ngày 05/11/2026
STT\tSẢN PHẨM\tMUA VÀO\tBÁN RA
1\tVÀNG MIẾNG SJC\t12,850\t13,350
2\tNHẪN TRÒN 9999 HƯNG THỊNH VƯỢNG\t12,800\t13,300
Đơn vị: Nghìn VND/chỉ"""


def test_doji_hourly_normalization_and_restart(db, settings, monkeypatch):
    db.get(DataSource, "doji").license_status = "licensed"
    db.commit()
    calls = []

    def fetch(self):
        observed = NOW + timedelta(hours=len(calls))
        calls.append(True)
        return parse_doji(TABLE, observed)

    monkeypatch.setattr(DojiGoldProvider, "fetch", fetch)
    assert collect_source(db, "doji", settings, now=NOW, hourly=True)["inserted"] == 2
    assert collect_source(db, "doji", settings, now=NOW, hourly=True)["reason"] == "hour_already_polled"
    assert collect_source(db, "doji", settings, now=NOW + timedelta(hours=1), hourly=True)["inserted"] == 2
    assert len(calls) == 2
    quote = db.scalar(
        select(QuoteSnapshot)
        .where(QuoteSnapshot.product_id == "doji-sjc-listed")
        .order_by(QuoteSnapshot.provider_timestamp)
    )
    assert (quote.bid, quote.ask) == (Decimal("128500000"), Decimal("133500000"))
    assert quote.provider_timestamp == NOW
    assert quote.time_basis == "board_observation"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Nghìn VND/chỉ", "Nghìn VND/lượng"),
        ("12,850", "12.850"),
        ("13,350", "10,000"),
        ("MUA VÀO\tBÁN RA", "BÁN RA\tMUA VÀO"),
        ("17:42", "18:42"),
    ],
)
def test_doji_rejects_ambiguous_or_invalid_table(old, new):
    with pytest.raises(SourceUnavailable):
        parse_doji(TABLE.replace(old, new), NOW)


def test_hourly_history_distinguishes_contracts_and_spot(db, settings):
    header = ",".join([*HEADERS, "contract"])
    lines = [
        header,
        "future,investing-gold,,2026-11-05T00:10:00+07:00,,,3000,USD/troy_oz,manual,GCZ2026",
        "future,investing-gold,,2026-11-05T00:42:00+07:00,,,3002,USD/troy_oz,manual,GCZ2026",
        "future,investing-gold,,2026-11-05T00:42:00+07:00,,,3010,USD/troy_oz,manual,GCG2027",
        "spot,manual-spot,,2026-11-05T02:42:00+07:00,,,2900,USD/troy_oz,manual,",
    ]
    obs = parse_csv("\n".join(lines).encode())
    assert ingest(db, obs, settings, now=NOW, rights_confirmed=True)["inserted"] == 4
    assert ingest(db, obs, settings, now=NOW, rights_confirmed=True)["duplicates"] == 4
    rows = hourly_history(db, date(2026, 11, 5), settings)
    assert [(r["symbol"], r["hour"], r["value"]) for r in rows] == [
        ("GCG2027", 0, 3010),
        ("GCZ2026", 0, 3002),
        ("XAU/USD", 2, 2900),
    ]
    assert db.scalars(select(FuturesSnapshot)).all()
    assert db.scalar(select(SpotSnapshot)).provider_id == "manual-spot"
    with pytest.raises(ValueError):
        parse_csv("\n".join([header, lines[1].replace("future,", "spot,")]).encode())


def test_sjc_board_preserves_published_time_and_vnd_per_luong():
    from app.providers.sjc import parse_sjc

    table = """Cập nhật lúc: 08:17 05/11/2026
Đơn vị tính: VNĐ / lượng
LOẠI VÀNG\tMUA\tBÁN
VÀNG SJC 1L, 10L, 1KG\t128,500,000\t133,500,000
VÀNG NHẪN SJC 99,99% 1 CHỈ, 2 CHỈ, 5 CHỈ\t127,300,000\t133,300,000"""
    a, b = parse_sjc(table, NOW)
    assert (a.ask, b.bid) == (133500000, 127300000)
    assert a.provider_timestamp.hour == 8 and a.time_basis == "provider"
    for invalid in (
        table.replace("VNĐ / lượng", "VNĐ / chỉ"),
        table + "\n" + table,
        table.replace("133,500,000", "133.500"),
    ):
        with pytest.raises(SourceUnavailable):
            parse_sjc(invalid, NOW)


def test_futures_parser_uses_contract_and_quote_timestamp():
    from app.providers.investing import parse_future

    fields = (
        "Gold (GCZ6)\nCurrency in USD\n100 Troy Ounces\nDec 26\n12/29/2026\n3,000.25\n2026-11-04T15:59:00Z"
    )
    (obs,) = parse_future(fields, NOW)
    assert (obs.kind, obs.contract, obs.value) == ("future", "GCZ2026", Decimal("3000.25"))
    assert obs.provider_timestamp.day == 4
    for old, new in [
        ("USD", "EUR"),
        ("GCZ6", "GCQ6"),
        ("Dec 26", "Dec 25"),
        ("Gold (GCZ6)", "Gold Spot"),
        ("00Z", "00"),
        ("3,000.25", "3.000,25"),
    ]:
        with pytest.raises(SourceUnavailable):
            parse_future(fields.replace(old, new), NOW)


@pytest.mark.parametrize("source", ["doji", "sjc", "investing-gold"])
def test_browser_sources_require_catalog_permission_and_enable(db, settings, source):
    unapproved = collect_source(db, source, settings, now=NOW)
    assert unapproved["error_code"] == "license_not_approved_in_catalog"
    db.get(DataSource, source).license_status = "licensed"
    db.commit()
    disabled = collect_source(db, source, settings, now=NOW)
    assert disabled["error_code"] == "source_disabled"
