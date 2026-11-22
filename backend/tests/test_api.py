from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import safe_csv_cell
from app.db import get_db
from app.ingestion.service import ingest, reconcile_day
from app.jobs.collect_daily import collect_source
from app.main import app
from app.providers.csv_provider import parse_csv
from app.providers.vang_today import SPOT_SOURCE_ID
from app.repositories.prices import history


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def loaded(db, settings):
    raw = (Path(__file__).parents[2] / "sample-data/quotes.sample.csv").read_bytes()
    ingest(db, parse_csv(raw), settings)
    for day in (date(2026, 11, 4), date(2026, 11, 5)):
        reconcile_day(db, day, settings)
    db.commit()


def test_health_and_empty_data(client):
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200
    products = client.get("/api/v1/catalog/products").json()["data"]
    assert sum(p["provider_id"] == "vang-today" for p in products) == 11
    assert any(product["id"] == "btmh-kgb-24k-listed" for product in products)
    response = client.get("/api/v1/quotes/latest?product_id=sjc-bar-1l-hcm").json()
    assert response["data"] is None and response["data_status"] == "missing"


def test_vang_today_world_quote_serves_latest_and_hourly(client, loaded, db, settings, monkeypatch):
    now = datetime(2026, 11, 5, 5, tzinfo=UTC)
    observed = now - timedelta(days=1)

    def fetch(timeout, allowlist, *, xauusd):
        assert xauusd
        return (
            f'{{"success":true,"type":"XAUUSD","timestamp":{int(observed.timestamp())},'
            '"buy":3539.25,"sell":0}'
        ).encode()

    assert client.get("/api/v1/prices/world/latest").json()["data"] is None
    monkeypatch.setattr("app.providers.vang_today.fetch_vang_today", fetch)
    assert collect_source(db, SPOT_SOURCE_ID, settings, now=observed, hourly=True)["inserted"] == 1
    observed = now
    assert collect_source(db, SPOT_SOURCE_ID, settings, now=now, hourly=True)["inserted"] == 1
    latest = client.get("/api/v1/prices/world/latest").json()
    assert latest["unit"] == "USD/troy_oz"
    assert latest["data"]["value"] == "3539.25000000"
    assert latest["data"]["source_url"] == "https://www.vang.today/api/prices?type=XAUUSD"
    hourly = client.get("/api/v1/prices/hourly?day=2026-11-05").json()["data"]
    row = next(point for point in hourly if point["source"] == SPOT_SOURCE_ID)
    assert row["kind"] == "spot" and row["hour"] == 12 and row["value"] == latest["data"]["value"]
    period = client.get("/api/v1/prices/hourly?from=2026-11-04&to=2026-11-05").json()["data"]
    assert [(p["business_date"], p["hour"]) for p in period if p["source"] == SPOT_SOURCE_ID] == [
        ("2026-11-04", 12), ("2026-11-05", 12)
    ]
    assert client.get("/api/v1/prices/hourly?from=2026-10-01&to=2026-11-05").status_code == 422


def test_history_precision_provenance_and_missing(client, loaded):
    response = client.get("/api/v1/prices/history?product_id=sjc-bar-1l-hcm&from=2026-11-03&to=2026-11-05")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert rows[0]["data_status"] == "missing"
    assert rows[1]["ask"] == "140000000.00000000"
    assert rows[1]["premium_status"] == "aligned_daily"
    assert rows[1]["data_status"] == "sample"
    assert rows[1]["spot"]["source"] == "manual-spot"


def test_btmh_quote_reaches_history_and_simulator_without_invented_world_price(client, db, settings):
    from datetime import UTC, datetime

    from app.models import DataSource
    from app.providers.btmh import PRODUCT_ID, parse_btmh

    db.get(DataSource, "btmh").license_status = "licensed"
    fixture = (Path(__file__).parent / "fixtures/btmh.sample.html").read_bytes()
    observed = datetime(2026, 11, 5, 11, tzinfo=UTC)
    ingest(db, parse_btmh(fixture, now=observed), settings, now=observed)
    reconcile_day(db, date(2026, 11, 5), settings)
    db.commit()
    latest = client.get(f"/api/v1/quotes/latest?product_id={PRODUCT_ID}").json()
    assert latest["data"]["ask"] == "141000000.00000000"
    assert latest["data"]["source"] == "btmh"
    response = client.get(f"/api/v1/prices/history?product_id={PRODUCT_ID}&from=2026-11-05&to=2026-11-05")
    quote = response.json()["data"][0]
    assert quote["premium_status"] == "missing" and quote["premium"] is None
    result = client.post(
        "/api/v1/simulations/historical",
        json={
            "product_id": PRODUCT_ID,
            "entry_date": "2026-11-05",
            "exit_date": "2026-11-05",
            "quantity": "1",
        },
    )
    assert result.status_code == 200
    assert result.json()["data"]["net_pnl_vnd"] == "-4000000.00000000"


def test_misaligned_premium_is_only_indicative(db, settings):
    raw = (Path(__file__).parents[2] / "sample-data/quotes.sample.csv").read_bytes()
    raw = raw.replace(b"2026-11-04T17:55:00+07:00,,,4000", b"2026-11-04T17:00:00+07:00,,,4000")
    ingest(db, parse_csv(raw), settings)
    reconcile_day(db, date(2026, 11, 4), settings)
    from app.models import GoldProduct

    rows = history(db, db.get(GoldProduct, "sjc-bar-1l-hcm"), date(2026, 11, 4), date(2026, 11, 4), settings)
    assert rows[0]["premium_status"] == "indicative_daily"
    assert rows[0]["timestamp_skew_seconds"] == 3600


def test_historical_exact_dates(client, loaded):
    body = {
        "product_id": "sjc-bar-1l-hcm",
        "entry_date": "2026-11-04",
        "exit_date": "2026-11-05",
        "quantity": "1",
    }
    response = client.post("/api/v1/simulations/historical", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["net_pnl_vnd"] == "-2000000.00000000"
    assert payload["data"]["holding_days"] == 1
    assert payload["data"]["entry"]["source"] == "sjc"
    assert payload["data_status"] == "sample"
    assert (
        client.post("/api/v1/simulations/historical", json={**body, "entry_date": "2026-11-03"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/simulations/historical", json={**body, "product_id": "pnj-ring-9999-hcm"}
        ).status_code
        == 422
    )
    manual = client.post(
        "/api/v1/simulations/historical",
        json={**body, "entry_date": "2026-11-03", "manual_entry_ask": "100000000"},
    ).json()
    assert manual["data"]["entry"]["reference_type"] == "manual"
    assert manual["data"]["net_pnl_vnd"] == "38000000.00000000"
    path = client.post("/api/v1/simulations/historical", json={**body, "include_path": True}).json()["data"][
        "path"
    ]
    assert len(path) == 2
    assert path[0]["net_pnl_vnd"] == "-3000000.00000000"
    assert path[1]["net_pnl_vnd"] == "-2000000.00000000"


SCENARIO = {
    "quantity": "1",
    "entry_ask": "140000000",
    "world_reference_now": "120000000",
    "world_change_pct": "0",
    "future_premium_pct": "10",
    "future_spread": "3000000",
}


def test_scenario_exact_and_label(client):
    result = client.post("/api/v1/simulations/scenario", json=SCENARIO)
    assert result.status_code == 200
    assert result.json()["data"]["net_pnl_vnd"] == "-11000000.0"
    assert result.json()["data"]["label"] == "SCENARIO, NOT OBSERVED PRICE"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "0", "-1", "1e2", 1.2, True, "0.000000001"])
def test_input_validation(client, value):
    assert (
        client.post("/api/v1/simulations/scenario", json={**SCENARIO, "quantity": value}).status_code == 422
    )


@pytest.mark.parametrize(
    "value", ["' OR 1=1--", "<script>alert(1)</script>", "../../.env", "https://127.0.0.1/"]
)
def test_query_injection(client, value):
    response = client.get("/api/v1/quotes/latest", params={"product_id": value})
    assert response.status_code == 422
    assert value not in response.text


def test_security_methods_body_size_headers(client):
    for path in ("/api/v1/ingest", "/api/v1/import", "/.env", "/api/v1/fetch", "/api/v1/sql"):
        assert client.post(path, json={}).status_code == 404
    assert client.post("/api/v1/catalog/products", json={}).status_code == 405
    assert (
        client.post(
            "/api/v1/simulations/scenario", content="x" * 20000, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert client.post("/api/v1/simulations/scenario", content="x").status_code == 415
    result = client.get("/api/v1/health/live")
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["cache-control"] == "no-store"


def test_range_limits_and_stats(client, loaded):
    assert (
        client.get(
            "/api/v1/prices/history?product_id=sjc-bar-1l-hcm&from=2020-01-01&to=2026-11-05"
        ).status_code
        == 422
    )
    url = "/api/v1/premiums/statistics?product_id=sjc-bar-1l-hcm&from=2026-11-04&to=2026-11-05"
    assert client.get(url).json()["data"]["count"] == 2


@pytest.mark.parametrize("value", [1793836800, "1793836800", "20261104", "2026-02-30"])
def test_strict_iso_date(client, value):
    body = {"product_id": "sjc-bar-1l-hcm", "entry_date": value, "quantity": "1"}
    assert client.post("/api/v1/simulations/historical", json=body).status_code == 422


@pytest.mark.parametrize("value", ["=HYPERLINK('x')", "+cmd", "-cmd", "@SUM(1)", "  =1+1", "\tcmd", "\rfoo"])
def test_csv_formula_injection(value):
    assert safe_csv_cell(value).startswith("'")


def test_hourly_endpoint_local_day_and_missing(client, loaded):
    result = client.get("/api/v1/prices/hourly?day=2026-11-05")
    assert result.status_code == 200
    body = result.json()
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert any(p["kind"] == "gold" and p["hour"] == 18 and p["reference_type"] == "sample" for p in body["data"])
    assert client.get("/api/v1/prices/hourly?day=2026-11-01").json()["data"] == []
    assert client.get("/api/v1/prices/hourly?day=2999-01-01").status_code == 422
