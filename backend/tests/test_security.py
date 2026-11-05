import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security import RequestGate
from app.config import Settings
from app.providers import safe_http
from app.providers.safe_http import SourceUnavailable


def test_rate_limit_cannot_be_bypassed_by_forwarded_headers():
    application = FastAPI()
    application.add_middleware(RequestGate, limit=2)

    @application.get("/read")
    def read():
        return {"ok": True}

    with TestClient(application) as client:
        assert client.get("/read").status_code == 200
        assert client.get("/read", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 200
        result = client.get("/read", headers={"X-Forwarded-For": "9.9.9.9"})
        assert result.status_code == 429 and result.headers["retry-after"] == "60"


def test_production_rejects_sqlite():
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(app_env="production", database_url="sqlite://")


def test_pinned_tls_redirects_retries_and_size(monkeypatch):
    calls = []
    responses = [
        httpx.Response(429),
        httpx.Response(503),
        httpx.Response(200, content=b"{}", headers={"content-type": "application/json"}),
    ]
    monkeypatch.setattr(safe_http, "public_addresses", lambda host: ["8.8.8.8"])
    monkeypatch.setattr(safe_http.time, "sleep", lambda seconds: None)
    actual_client = httpx.Client

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
            self.client = actual_client(transport=httpx.MockTransport(self.handle))

        def handle(self, request):
            calls.append(request)
            return responses.pop(0)

        def __enter__(self):
            return self.client

        def __exit__(self, *args):
            self.client.close()

    monkeypatch.setattr(safe_http.httpx, "Client", Client)
    assert safe_http.fetch_spot("fixture-key-not-real", 10, "api.metals.dev") == b"{}"
    assert len(calls) == 3
    assert calls[0].url.host == "8.8.8.8"
    assert calls[0].headers["Host"] == "api.metals.dev"
    assert calls[0].extensions["sni_hostname"] == "api.metals.dev"
    responses.append(httpx.Response(302, headers={"Location": "http://169.254.169.254/"}))
    with pytest.raises(SourceUnavailable, match="http_error"):
        safe_http.fetch_spot("fixture-key-not-real", 10, "api.metals.dev")
    responses.append(
        httpx.Response(
            200,
            content=b"x" * (safe_http.MAX_RESPONSE_BYTES + 1),
            headers={"content-type": "application/json"},
        )
    )
    with pytest.raises(SourceUnavailable, match="too_large"):
        safe_http.fetch_spot("fixture-key-not-real", 10, "api.metals.dev")
