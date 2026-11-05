from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import safe_csv_cell
from app.db import get_db
from app.ingestion.service import ingest, reconcile_day
from app.main import app
from app.providers.csv_provider import parse_csv
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
    assert len(client.get("/api/v1/catalog/products").json()["data"]) == 4
    response = client.get("/api/v1/quotes/latest?product_id=sjc-bar-1l-hcm").json()
    assert response["data"] is None and response["data_status"] == "missing"


def test_history_precision_provenance_and_missing(client, loaded):
    response = client.get("/api/v1/prices/history?product_id=sjc-bar-1l-hcm&from=2026-11-03&to=2026-11-05")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert rows[0]["data_status"] == "missing"
    assert rows[1]["ask"] == "140000000.00000000"
    assert rows[1]["premium_status"] == "aligned_daily"
    assert rows[1]["data_status"] == "sample"
    assert rows[1]["spot"]["source"] == "manual-spot"


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
