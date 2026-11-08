"""BTMH's public HTML price table. Never executes embedded JavaScript or follows links."""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from app.config import Settings
from app.providers.base import Observation
from app.providers.safe_http import MAX_HTML_BYTES, SourceUnavailable, fetch_btmh

PARSER_VERSION = "btmh-html-v1"
PRODUCT_ID = "btmh-kgb-24k-listed"
PRODUCT_NAME = "Kim Gia Bảo 24K"
SOURCE_URL = "https://baotinmanhhai.vn/bang-gia-vang"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
IGNORED_TAGS = frozenset({"script", "style", "svg", "template"})


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)

    def elements(self):
        return [child for child in self.children if isinstance(child, Element)]

    def text(self) -> str:
        if self.tag in IGNORED_TAGS:
            return ""
        value = " ".join(child.text() if isinstance(child, Element) else child for child in self.children)
        return " ".join(unicodedata.normalize("NFC", value).split())

    def descendants(self):
        pending = [self]
        while pending:
            node = pending.pop()
            yield node
            pending.extend(reversed(node.elements()))


class PriceHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 30000 or len(self.stack) > 80:
            raise ValueError("html_complexity_limit")
        if len({key for key, _ in attrs}) != len(attrs):
            raise ValueError("duplicate_attributes")
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise ValueError("malformed_html")
        self.stack.pop()

    def handle_data(self, data):
        if self.stack[-1].tag not in IGNORED_TAGS:
            self.stack[-1].children.append(data)


def _one(items):
    if len(items) != 1:
        raise ValueError("ambiguous_or_missing_element")
    return items[0]


def _parse(payload: bytes, now: datetime, max_age_hours: int) -> Observation:
    if not payload or len(payload) > MAX_HTML_BYTES:
        raise ValueError("html_size_limit")
    parser = PriceHTML()
    parser.feed(payload.decode("utf-8-sig", errors="strict"))
    parser.close()
    if len(parser.stack) != 1:
        raise ValueError("unclosed_html")
    section = _one(
        [
            node
            for node in parser.root.descendants()
            if (node.attrs.get("id") or "").startswith("gold_price_table-")
            and any(child.tag == "h2" and child.text() == "Giá vàng hôm nay" for child in node.descendants())
        ]
    )
    _one([node for node in section.descendants() if node.tag == "h2" and node.text() == "Giá vàng hôm nay"])
    groups = [node for node in section.descendants() if node.attrs.get("role") == "rowgroup"]
    if len(groups) != 2:
        raise ValueError("rowgroup_schema_changed")
    headers = groups[0].elements()
    if [node.attrs.get("role") for node in headers] != ["columnheader"] * 5 or [
        node.text() for node in headers
    ] != ["Loại vàng", "Hàm lượng (%)", "Đơn giá (nghìn VNĐ) Mua vào Bán ra", "Biến động", "Biểu đồ"]:
        raise ValueError("header_schema_changed")
    price_header = headers[2].elements()
    if len(price_header) != 2 or [node.text() for node in price_header[1].elements()] != [
        "Mua vào",
        "Bán ra",
    ]:
        raise ValueError("price_column_order_changed")
    rows = groups[1].elements()
    if not rows or any(row.attrs.get("role") != "row" for row in rows):
        raise ValueError("row_schema_changed")
    row = _one([row for row in rows if row.elements() and row.elements()[0].text() == PRODUCT_NAME])
    cells = row.elements()
    if len(cells) != 6 or cells[0].attrs.get("role") != "cell" or cells[1].attrs.get("role") != "cell":
        raise ValueError("cell_schema_changed")
    if cells[1].text() != "99.99":
        raise ValueError("purity_changed")
    table_text = section.text()
    if table_text.count("Đơn vị tính (ĐVT): chỉ") != 1 or table_text.count("Cập nhật lúc") != 1:
        raise ValueError("unit_or_timestamp_changed")
    timestamp = _one(
        re.findall(r"Cập nhật lúc (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s*\)", table_text)
    )
    observed_at = datetime.fromisoformat(timestamp).replace(tzinfo=VN)
    if observed_at > now + timedelta(minutes=5):
        raise SourceUnavailable("provider_timestamp_in_future")
    if now - observed_at > timedelta(hours=max_age_hours):
        raise SourceUnavailable("provider_data_stale")
    raw_bid, raw_ask = cells[2].text(), cells[3].text()
    if any(
        not re.fullmatch(r"(?:0|[1-9]\d{0,8}|[1-9]\d{0,2}(?:\.\d{3}){1,2})", value, re.ASCII)
        for value in (raw_bid, raw_ask)
    ):
        raise ValueError("invalid_price_format")
    # The selected product's verified convention is thousand VND / chi, ten chi / luong.
    bid, ask = (Decimal(value.replace(".", "")) * Decimal("10000") for value in (raw_bid, raw_ask))
    # Hash only the source quote fields, so ads, charts and other products cannot cause false conflicts.
    # The original HTTP document is not retained or executed by this adapter.
    raw_quote = {
        "source_url": SOURCE_URL,
        "product": PRODUCT_NAME,
        "purity": "99.99",
        "timestamp": timestamp,
        "timezone": "Asia/Ho_Chi_Minh",
        "unit": "thousand_VND/chi",
        "bid": raw_bid,
        "ask": raw_ask,
        "normalized_bid": str(bid),
        "normalized_ask": str(ask),
    }
    digest = hashlib.sha256(json.dumps(raw_quote, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return Observation(
        kind="gold",
        provider_id="btmh",
        product_id=PRODUCT_ID,
        provider_timestamp=observed_at,
        bid=bid,
        ask=ask,
        unit="VND/luong",
        reference_type="official",
        raw_payload_hash=digest,
    )


def parse_btmh(payload: bytes, *, now: datetime | None = None, max_age_hours: int = 24) -> list[Observation]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now requires timezone")
    try:
        return [_parse(payload, now, max_age_hours)]
    except (ValueError, TypeError, IndexError, OverflowError):
        raise SourceUnavailable("provider_schema_changed") from None


class BtmhGoldProvider:
    provider_id = "btmh"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.btmh_enabled:
            raise SourceUnavailable("source_disabled")
        if not self.settings.btmh_license_confirmed:
            raise SourceUnavailable("data_rights_not_confirmed")
        if not self.settings.btmh_conventions_confirmed:
            raise SourceUnavailable("units_or_timezone_not_confirmed")
        return parse_btmh(
            fetch_btmh(
                self.settings.request_timeout_seconds,
                self.settings.source_allowlist,
                self.settings.btmh_min_interval_minutes,
            ),
            max_age_hours=self.settings.btmh_max_age_hours,
        )
