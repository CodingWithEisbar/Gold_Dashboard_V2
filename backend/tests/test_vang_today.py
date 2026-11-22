import json
from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.collect_daily import collect_source
from app.models import GoldProduct, QuoteSnapshot
from app.providers.safe_http import SourceUnavailable
from app.providers.vang_today import VangTodayGoldProvider, parse_prices

NOW = datetime(2026, 11, 22, 8, tzinfo=UTC)


def board():
    return {
        "success": True, "timestamp": int(NOW.timestamp()),
        "prices": {
            "DOHNL": {"currency": "VND", "buy": 120000000, "sell": 123000000},
            "XAUUSD": {"currency": "USD", "buy": 3000, "sell": 0},
        },
    }


def test_public_feed_keeps_market_time_brand_unit_and_duplicates(db, settings, monkeypatch):
    reply = board()
    monkeypatch.setattr(VangTodayGoldProvider, "fetch", lambda self: parse_prices(json.dumps(reply).encode()))
    assert collect_source(db, "vang-today", settings, now=NOW, hourly=True)["inserted"] == 1
    reply["prices"]["DOHNL"]["change_buy"] = 20000
    assert collect_source(db, "vang-today", settings, now=NOW + timedelta(hours=1), hourly=True)["duplicates"] == 1
    quote = db.query(QuoteSnapshot).one()
    assert quote.product_id == "vang-today-dohnl" and quote.provider_timestamp == NOW
    assert quote.bid == 120000000 and quote.ask == 123000000 and quote.unit == "VND/luong"
    assert quote.source_url == "https://www.vang.today/api/prices"
    assert db.get(GoldProduct, quote.product_id).purity is None


@pytest.mark.parametrize("change", [{"currency": "USD"}, {"buy": True}, {"sell": 0}, {"buy": 124000000}])
def test_bad_domestic_quote_rejected(change):
    data = board()
    data["prices"]["DOHNL"].update(change)
    with pytest.raises(SourceUnavailable):
        parse_prices(json.dumps(data).encode())
