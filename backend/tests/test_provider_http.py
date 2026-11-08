import socket
import ssl
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.providers import safe_http as http


def mock_http(monkeypatch, handler):
    original = httpx.Client

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        assert isinstance(kwargs["verify"], ssl.SSLContext)
        assert kwargs["verify"].check_hostname and kwargs["verify"].verify_mode == ssl.CERT_REQUIRED
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(http.httpx, "Client", client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    sleeps = []
    monkeypatch.setattr(http.time, "sleep", sleeps.append)
    return sleeps


def test_pinned_ip_host_sni_and_fixed_paths(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"safe HTML")

    mock_http(monkeypatch, handler)
    assert http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST) == b"safe HTML"
    request = requests[0]
    assert request.url.host == "93.184.216.34" and request.url.scheme == "https"
    assert request.headers["Host"] == http.BTMH_HOST
    assert request.extensions["sni_hostname"] == http.BTMH_HOST
    for host, path, allow in (
        ("evil.example", "/", "evil.example"),
        (http.BTMH_HOST, "/admin", http.BTMH_HOST),
        (http.BTMH_HOST, http.BTMH_PATH, "api.metals.dev"),
    ):
        with pytest.raises(http.SourceUnavailable, match="not_allowed"):
            http._fetch(host, path, 10, allow)
    assert len(requests) == 1


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fd00::1"])
def test_all_dns_answers_are_validated_for_btmh(monkeypatch, address):
    mock_http(monkeypatch, lambda request: pytest.fail("Private IP must not be contacted"))
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", (address, 443))],
    )
    with pytest.raises(http.SourceUnavailable, match="non_public_address"):
        http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST)


@pytest.mark.parametrize(
    ("status", "headers", "body", "code"),
    [
        (302, {"location": "http://169.254.169.254/"}, b"", "provider_http_error"),
        (403, {}, b"CAPTCHA", "provider_http_error"),
        (200, {"content-type": "application/json"}, b"{}", "unexpected_content_type"),
        (200, {"content-type": "text/html", "content-encoding": "gzip"}, b"", "unexpected_content_encoding"),
        (200, {"content-type": "text/html"}, b"x" * (http.MAX_HTML_BYTES + 1), "response_too_large"),
    ],
)
def test_http_response_guards(monkeypatch, status, headers, body, code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers=headers, content=body)

    sleeps = mock_http(monkeypatch, handler)
    with pytest.raises(http.SourceUnavailable, match=code):
        http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST)
    assert len(requests) == 1 and sleeps == []


def test_rate_limit_retry_after_and_retry_limit(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) < 3:
            return httpx.Response(429, headers={"retry-after": "3"})
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

    sleeps = mock_http(monkeypatch, handler)
    assert http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST) == b"ok"
    assert len(requests) == 3 and len(sleeps) == 2 and all(delay >= 3 for delay in sleeps)


def test_long_retry_after_defers_instead_of_retrying_early(monkeypatch):
    sleeps = mock_http(monkeypatch, lambda r: httpx.Response(429, headers={"retry-after": "3600"}))
    with pytest.raises(http.SourceUnavailable, match="retry_after_exceeds_budget"):
        http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST)
    assert sleeps == []
    with pytest.raises(http.SourceUnavailable, match="retry_after_exceeds_budget"):
        http.retry_delay(format_datetime(datetime.now(UTC) + timedelta(hours=1)), 0)


def test_final_attempt_preserves_long_retry_after(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return (
            httpx.Response(503) if len(requests) < 3 else httpx.Response(429, headers={"retry-after": "3600"})
        )

    mock_http(monkeypatch, handler)
    with pytest.raises(http.SourceUnavailable, match="retry_after_exceeds_budget") as caught:
        http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST)
    assert len(requests) == 3 and caught.value.retry_after_seconds == 3600


def test_response_deadline_is_enforced(monkeypatch):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=b"html"),
    )
    clock = iter((0, 31))
    monkeypatch.setattr(http.time, "monotonic", lambda: next(clock))
    with pytest.raises(http.SourceUnavailable, match="response_deadline_exceeded"):
        http._fetch(http.BTMH_HOST, http.BTMH_PATH, 10, http.BTMH_HOST)


@pytest.mark.parametrize("failure", ["timeout", "server"])
def test_transport_and_server_failures_are_bounded_and_sanitized(monkeypatch, failure):
    requests = []

    def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive provider detail", request=request)
        return httpx.Response(503)

    sleeps = mock_http(monkeypatch, handler)
    with pytest.raises(http.SourceUnavailable, match="transport_failed|retry_exhausted"):
        http.fetch_spot("test-key-not-a-secret", 10, "api.metals.dev")
    assert len(requests) == 3 and len(sleeps) == 2


@pytest.mark.parametrize(
    ("robots", "error"),
    [
        (b"User-agent: *\nDisallow: /bang-gia-vang", "robots_disallowed"),
        (b"User-agent: *\nCrawl-delay: 3600", "robots_rate_exceeds_schedule"),
        (b"User-agent: *\nRequest-rate: 1/3600", "robots_rate_exceeds_schedule"),
        (b"not a robots file", "robots_invalid"),
        (b"\xff", "robots_invalid"),
    ],
)
def test_robots_blocks_price_request(monkeypatch, robots, error):
    paths = []

    def fetch(host, path, timeout, allowlist):
        paths.append(path)
        return robots

    monkeypatch.setattr(http, "_fetch", fetch)
    with pytest.raises(http.SourceUnavailable, match=error):
        http.fetch_btmh(10, http.BTMH_HOST, 30)
    assert paths == ["/robots.txt"]


def test_robots_allows_only_fixed_price_page(monkeypatch):
    paths = []

    def fetch(host, path, timeout, allowlist):
        paths.append(path)
        return b"User-agent: *\nAllow: /" if path == "/robots.txt" else b"html"

    monkeypatch.setattr(http, "_fetch", fetch)
    assert http.fetch_btmh(10, http.BTMH_HOST, 30) == b"html"
    assert paths == ["/robots.txt", "/bang-gia-vang"]
