"""Pinned-IP TLS requests prevent DNS rebinding. Redirects and environment proxies are disabled."""

import ipaddress
import random
import socket
import ssl
import time
from urllib.parse import urlencode

import httpx

FIXED_HOST = "api.metals.dev"
FIXED_PATH = "/v1/metal/spot"
MAX_RESPONSE_BYTES = 256 * 1024


class SourceUnavailable(Exception):
    pass


def public_addresses(host: str) -> list[str]:
    if host != FIXED_HOST:
        raise SourceUnavailable("host_not_allowed")
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError:
        raise SourceUnavailable("dns_failed") from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise SourceUnavailable("non_public_address")
    return addresses


def fetch_spot(api_key: str, timeout: int, allowlist: str) -> bytes:
    if FIXED_HOST not in {host.strip() for host in allowlist.split(",")}:
        raise SourceUnavailable("host_not_allowed")
    for attempt in range(3):
        # Resolve again on retries; validate *all* answers and connect directly to the selected public IP.
        address = public_addresses(FIXED_HOST)[0]
        address = f"[{address}]" if ":" in address else address
        url = f"https://{address}{FIXED_PATH}?{urlencode({'api_key': api_key, 'metal': 'gold', 'currency': 'USD'})}"
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=False, trust_env=False, verify=ssl.create_default_context()
            ) as client:
                with client.stream(
                    "GET",
                    url,
                    headers={"Host": FIXED_HOST, "Accept": "application/json", "Accept-Encoding": "identity"},
                    extensions={"sni_hostname": FIXED_HOST},
                ) as response:
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt == 2:
                            raise SourceUnavailable("retry_exhausted")
                    elif response.status_code != 200:
                        raise SourceUnavailable("provider_http_error")
                    else:
                        if "application/json" not in response.headers.get("content-type", ""):
                            raise SourceUnavailable("unexpected_content_type")
                        payload = bytearray()
                        for chunk in response.iter_bytes():
                            payload.extend(chunk)
                            if len(payload) > MAX_RESPONSE_BYTES:
                                raise SourceUnavailable("response_too_large")
                        return bytes(payload)
        except httpx.TransportError:
            if attempt == 2:
                raise SourceUnavailable("transport_failed") from None
        # Not used for security decisions; bounded retry jitter.
        time.sleep(2**attempt + random.SystemRandom().uniform(0, 0.5))
    raise SourceUnavailable("retry_exhausted")
