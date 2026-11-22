"""Read the domestic gold table displayed by DOJI's public browser application."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import Settings
from app.providers.base import Observation
from app.providers.browser_board import DOJI_URL, read_board
from app.providers.btmh import VN
from app.providers.safe_http import SourceUnavailable

PRODUCTS = {"VÀNG MIẾNG SJC": "doji-sjc-listed", "NHẪN TRÒN 9999 HƯNG THỊNH VƯỢNG": "doji-ring-9999-listed"}
TITLE = "BẢNG GIÁ VÀNG DOJI"
UNIT = "Đơn vị: Nghìn VND/chỉ"
PRICE = re.compile(r"[1-9][0-9]{0,2}(?:,[0-9]{3})*")


def parse_doji(body: str, now: datetime) -> list[Observation]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    try:
        if lines.count(TITLE) != 1:
            raise ValueError
        start = lines.index(TITLE)
        end = lines.index(UNIT, start)
        stamp = datetime.strptime(lines[start + 1], "Cập nhật %H:%M ngày %d/%m/%Y").replace(tzinfo=VN)
        if stamp > now + timedelta(minutes=5) or now - stamp > timedelta(days=1):
            raise SourceUnavailable("provider_timestamp_out_of_range")
        if lines[start + 2].split("\t") != ["STT", "SẢN PHẨM", "MUA VÀO", "BÁN RA"]:
            raise ValueError
        quotes = {}
        for row in lines[start + 3 : end]:
            cells = row.split("\t")
            if len(cells) < 2:
                raise ValueError
            name = cells[1]
            if name not in PRODUCTS:
                continue
            if name in quotes or len(cells) != 4 or not all(PRICE.fullmatch(v) for v in cells[2:]):
                raise ValueError
            bid, ask = (Decimal(v.replace(",", "")) * 10000 for v in cells[2:])
            # The DOJI page localizes its clock to the viewing browser. It gives no
            # independently verified exchange/publication timestamp for this row.
            identity = "|".join((name, now.isoformat(), UNIT, *cells[2:]))
            quotes[name] = Observation(
                kind="gold",
                provider_id="doji",
                product_id=PRODUCTS[name],
                provider_timestamp=now,
                time_basis="board_observation",
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


class DojiGoldProvider:
    provider_id = "doji"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.doji_enabled:
            raise SourceUnavailable("source_disabled")
        return parse_doji(read_board(DOJI_URL, (TITLE, UNIT)), datetime.now(UTC))
