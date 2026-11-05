import json
import socket
from decimal import Decimal

import pytest

from app.providers.metals_dev import parse_spot
from app.providers.safe_http import SourceUnavailable, public_addresses


def test_decimal_parser_and_schema_change():
    fixture = {
        "status": "success",
        "currency": "USD",
        "unit": "toz",
        "metal": "gold",
        "timestamp": "2026-11-05T10:59:00Z",
        "rate": {"price": "4000.12345678"},
    }
    result = parse_spot(json.dumps(fixture).encode())[0]
    assert result.value == Decimal("4000.12345678")
    with pytest.raises(SourceUnavailable, match="schema_changed"):
        parse_spot(json.dumps({**fixture, "unit": "g"}).encode())
    with pytest.raises(SourceUnavailable):
        parse_spot(b'{"rate": NaN}')


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fd00::1", "::ffff:127.0.0.1"]
)
def test_ssrf_private_dns(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(SourceUnavailable, match="non_public"):
        public_addresses("api.metals.dev")


def test_ssrf_host_allowlist():
    with pytest.raises(SourceUnavailable, match="not_allowed"):
        public_addresses("evil.example")
