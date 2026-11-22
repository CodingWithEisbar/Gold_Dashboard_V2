"""Normalize the product groups on SJC's public price board."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import Settings
from app.providers.base import Observation
from app.providers.browser_board import SJC_URL, read_board
from app.providers.btmh import VN
from app.providers.safe_http import SourceUnavailable

UNIT = "Đơn vị tính: VNĐ / lượng"
HEADER = "LOẠI VÀNG\tMUA\tBÁN"
PRODUCTS = {
    "VÀNG SJC 1L, 10L, 1KG": "sjc-bar-listed",
    "VÀNG NHẪN SJC 99,99% 1 CHỈ, 2 CHỈ, 5 CHỈ": "sjc-ring-listed",
}


def parse_sjc(body: str, now: datetime) -> list[Observation]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    try:
        stamps = [line for line in lines if line.startswith("Cập nhật lúc:")]
        if len(stamps) != 1 or lines.count(UNIT) != 1 or lines.count(HEADER) != 1:
            raise ValueError
        stamp = datetime.strptime(stamps[0], "Cập nhật lúc: %H:%M %d/%m/%Y").replace(tzinfo=VN)
        if stamp > now + timedelta(minutes=5):
            raise SourceUnavailable("provider_timestamp_in_future")
        quotes = {}
        for line in lines[lines.index(HEADER) + 1 :]:
            name, *prices = line.split("\t")
            if name not in PRODUCTS:
                continue
            if (
                name in quotes
                or len(prices) != 2
                or not all(re.fullmatch(r"[1-9][0-9]{0,2}(?:,[0-9]{3})*", p) for p in prices)
            ):
                raise ValueError
            bid, ask = (Decimal(p.replace(",", "")) for p in prices)
            identity = "|".join((name, stamp.isoformat(), UNIT, *prices))
            quotes[name] = Observation(
                kind="gold",
                provider_id="sjc",
                product_id=PRODUCTS[name],
                provider_timestamp=stamp,
                bid=bid,
                ask=ask,
                unit="VND/luong",
                reference_type="official",
                raw_payload_hash=hashlib.sha256(identity.encode()).hexdigest(),
            )
        if quotes.keys() != PRODUCTS.keys():
            raise ValueError
        return list(quotes.values())
    except (ValueError, IndexError):
        raise SourceUnavailable("provider_schema_changed") from None


class SjcGoldProvider:
    provider_id = "sjc"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.sjc_enabled:
            raise SourceUnavailable("source_disabled")
        body = read_board(SJC_URL, (UNIT, *PRODUCTS))
        return parse_sjc(body, datetime.now(UTC))
