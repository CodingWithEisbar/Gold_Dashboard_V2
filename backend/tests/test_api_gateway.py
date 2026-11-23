from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_db
from app.ingestion.service import record_run
from app.main import app


def test_records_get_and_post_and_protects_gateway(tmp_path, monkeypatch, db):
    monkeypatch.setenv("API_LOG_PATH", str(tmp_path / "log.sqlite3"))
    monkeypatch.setenv("API_GATEWAY_TOKEN", "fixture-only-monitor-token")
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: db
    try:
        record_run(db, "vang-today", "success", counts={"inserted": 11})
        db.commit()
        with TestClient(app) as client:
            assert client.get("/api/v1/health/live?input=PRIVATE_QUERY").status_code == 200
            assert client.post("/api/v1/simulations/scenario", json={"input": "PRIVATE_BODY"}).status_code == 422
            assert client.post("/api/v1/simulations/scenario", content="bad").status_code == 415
            assert client.get("/api/v1/PRIVATE_PATH").status_code == 404
            assert client.get("/api/v1/gateway/requests").status_code == 401
            headers = {"Authorization": "Bearer fixture-only-monitor-token"}
            response = client.get("/api/v1/gateway/requests", headers=headers)
            assert response.status_code == 200
            assert "PRIVATE_" not in response.text and "fixture-only-monitor-token" not in response.text
            all_logs = response.json()["data"]
            assert [(row["method"], row["endpoint"], row["status"]) for row in all_logs] == [
                ("GET", "(unknown)", 404),
                ("POST", "/api/v1/simulations/scenario", 415),
                ("POST", "/api/v1/simulations/scenario", 422),
                ("GET", "/api/v1/health/live", 200),
            ]
            posts = client.get("/api/v1/gateway/requests?method=POST&status_class=4", headers=headers)
            assert posts.json()["data"] == all_logs[1:3]
            runs = client.get("/api/v1/gateway/ingestion-runs", headers=headers)
            assert runs.status_code == 200 and runs.json()["data"][0]["inserted"] == 11

        with TestClient(app) as client:
            assert client.get("/api/v1/gateway/requests", headers=headers).json()["data"] == all_logs
    finally:
        app.dependency_overrides.pop(get_db)
        get_settings.cache_clear()
