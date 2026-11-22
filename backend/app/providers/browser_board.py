"""Read visible text from fixed public price boards through a dedicated WebDriver."""

import time

import httpx

from app.providers.safe_http import SourceUnavailable

DOJI_URL = "https://banggia.doji.vn/gold-price"
SJC_URL = "https://sjc.com.vn/gia-vang-online"
INVESTING_URL = "https://www.investing.com/commodities/gold"
BOARD_TEXT = "return [location.href, document.body.innerText.slice(0, 40000)]"


def read_board(url: str, markers: tuple[str, ...], *, script: str = BOARD_TEXT) -> str:
    if url not in {DOJI_URL, SJC_URL, INVESTING_URL}:
        raise SourceUnavailable("host_not_allowed")
    # The isolated browser receives only a fixed public URL and no credentials.
    with httpx.Client(base_url="http://price-browser:4444", timeout=35, trust_env=False) as client:
        session = None
        try:
            created = (
                client.post(
                    "/session",
                    json={
                        "capabilities": {
                            "alwaysMatch": {
                                "browserName": "firefox",
                                "pageLoadStrategy": "eager",
                                "timeouts": {"pageLoad": 20000},
                            }
                        }
                    },
                )
                .raise_for_status()
                .json()["value"]
            )
            session = "/session/" + created["sessionId"]
            client.post(session + "/url", json={"url": url}).raise_for_status()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                document = (
                    client.post(session + "/execute/sync", json={"script": script, "args": []})
                    .raise_for_status()
                    .json()["value"]
                )
                location, body = document
                if location != url:
                    raise SourceUnavailable("unexpected_page_location")
                if all(marker in body for marker in markers):
                    return body
                time.sleep(0.5)
            raise SourceUnavailable("price_table_unavailable")
        except (httpx.HTTPError, TypeError, KeyError, ValueError):
            raise SourceUnavailable("browser_unavailable") from None
        finally:
            if session:
                try:
                    client.delete(session)
                except httpx.HTTPError:
                    pass  # The Grid also expires abandoned sessions.
