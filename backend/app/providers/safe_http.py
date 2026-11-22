"""Fixed HTTPS endpoints, pinned public IPs, verified TLS, and bounded retries."""

import ipaddress
import math
import random
import socket
import ssl
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.robotparser import RobotFileParser

import httpx

FIXED_HOST = "api.metals.dev"
FIXED_PATH = "/v1/metal/spot"
BTMH_HOST = "baotinmanhhai.vn"
BTMH_PATH = "/bang-gia-vang"
USER_AGENT = "GoldPremiumTracker/1.0"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
VANG_HOST = "www.vang.today"
VANG_PATH = "/api/prices"
ENDPOINTS = {
    (VANG_HOST, VANG_PATH): ("application/json", MAX_RESPONSE_BYTES),
    (FIXED_HOST, FIXED_PATH): ("application/json", MAX_RESPONSE_BYTES),
    (BTMH_HOST, BTMH_PATH): ("text/html", MAX_HTML_BYTES),
    (BTMH_HOST, "/robots.txt"): ("text/plain", 16 * 1024),
}


class SourceUnavailable(Exception):
    def __init__(self, code: str, *, retry_after_seconds: int | None = None):
        super().__init__(code)
        self.retry_after_seconds = retry_after_seconds


def public_addresses(host: str) -> list[str]:
    if host not in {FIXED_HOST, BTMH_HOST, VANG_HOST}:
        raise SourceUnavailable("host_not_allowed")
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError:
        raise SourceUnavailable("dns_failed") from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise SourceUnavailable("non_public_address")
    return addresses


def retry_delay(value: str | None, attempt: int) -> float:
    delay = 2**attempt + random.SystemRandom().uniform(0, 0.5)
    if value:
        try:
            seconds = (
                int(value)
                if value.isascii() and value.isdigit()
                else (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            )
            # Never retry earlier than Retry-After; defer long waits to the next scheduled run.
            if seconds > 10:
                raise SourceUnavailable("retry_after_exceeds_budget", retry_after_seconds=math.ceil(seconds))
            delay = max(delay, seconds)
        except (ValueError, TypeError, OverflowError):
            pass
    return delay


def _fetch(host: str, path: str, timeout: int, allowlist: str, *, query: dict | None = None) -> bytes:
    if (host, path) not in ENDPOINTS or host not in {item.strip() for item in allowlist.split(",")}:
        raise SourceUnavailable("host_not_allowed")
    accept, maximum = ENDPOINTS[(host, path)]
    for attempt in range(3):
        address = public_addresses(host)[0]
        address = f"[{address}]" if ":" in address else address
        url = f"https://{address}{path}" + (f"?{urlencode(query)}" if query else "")
        delay = None
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=False, trust_env=False, verify=ssl.create_default_context()
            ) as client:
                with client.stream(
                    "GET",
                    url,
                    headers={
                        "Host": host,
                        "Accept": accept,
                        "Accept-Encoding": "identity",
                        "User-Agent": USER_AGENT,
                    },
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.status_code == 429 or response.status_code >= 500:
                        delay = retry_delay(response.headers.get("retry-after"), attempt)
                        if attempt == 2:
                            raise SourceUnavailable("retry_exhausted")
                    elif response.status_code != 200:
                        raise SourceUnavailable("provider_http_error")
                    else:
                        if response.headers.get("content-type", "").split(";", 1)[0].strip() != accept:
                            raise SourceUnavailable("unexpected_content_type")
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise SourceUnavailable("unexpected_content_encoding")
                        payload = bytearray()
                        started = time.monotonic()
                        for chunk in response.iter_bytes(chunk_size=16 * 1024):
                            payload.extend(chunk)
                            if len(payload) > maximum:
                                raise SourceUnavailable("response_too_large")
                            if time.monotonic() - started > 30:
                                raise SourceUnavailable("response_deadline_exceeded")
                        return bytes(payload)
        except httpx.TransportError:
            if attempt == 2:
                raise SourceUnavailable("transport_failed") from None
        time.sleep(delay if delay is not None else retry_delay(None, attempt))
    raise SourceUnavailable("retry_exhausted")


def fetch_spot(api_key: str, timeout: int, allowlist: str) -> bytes:
    return _fetch(
        FIXED_HOST,
        FIXED_PATH,
        timeout,
        allowlist,
        query={"api_key": api_key, "metal": "gold", "currency": "USD"},
    )


def fetch_vang_today(timeout: int, allowlist: str, *, xauusd: bool = False) -> bytes:
    query = {"type": "XAUUSD"} if xauusd else None
    return _fetch(VANG_HOST, VANG_PATH, timeout, allowlist, query=query)


def fetch_btmh(timeout: int, allowlist: str, interval_minutes: int) -> bytes:
    robots = _fetch(BTMH_HOST, "/robots.txt", timeout, allowlist)
    try:
        lines = robots.decode("utf-8-sig").splitlines()
        if not any(
            line.lower().strip().startswith("user-agent:") and line.split(":", 1)[1].strip() for line in lines
        ):
            raise ValueError("missing_user_agent")
        parser = RobotFileParser()
        parser.parse(lines)
    except (ValueError, UnicodeError):
        raise SourceUnavailable("robots_invalid") from None
    if not parser.can_fetch(USER_AGENT, f"https://{BTMH_HOST}{BTMH_PATH}"):
        raise SourceUnavailable("robots_disallowed")
    delay = parser.crawl_delay(USER_AGENT)
    rate = parser.request_rate(USER_AGENT)
    if (delay and delay > interval_minutes * 60) or (
        rate and (rate.requests <= 0 or rate.seconds / rate.requests > interval_minutes * 60)
    ):
        raise SourceUnavailable("robots_rate_exceeds_schedule")
    return _fetch(BTMH_HOST, BTMH_PATH, timeout, allowlist)
