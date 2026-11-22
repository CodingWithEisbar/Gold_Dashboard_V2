"""Domestic VND/tael and XAU/USD prices from the Vàng.Today public API."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from app.config import Settings
from app.providers.base import Observation
from app.providers.safe_http import SourceUnavailable, fetch_vang_today

SOURCE_ID = "vang-today"
SOURCE_URL = "https://www.vang.today/api/prices"
SPOT_SOURCE_ID = "vang-today-xauusd"
SPOT_SOURCE_URL = SOURCE_URL + "?type=XAUUSD"
# Product name, issuer, market and fineness (only when identified by the feed).
PRODUCTS = {
    "SJL1L10": ("SJC 9999", "SJC", "Việt Nam", "0.9999"),
    "SJ9999": ("Nhẫn SJC", "SJC", "Việt Nam", "0.9999"),
    "DOHNL": ("DOJI Hà Nội", "DOJI", "Hà Nội", None),
    "DOHCML": ("DOJI HCM", "DOJI", "TP.HCM", None),
    "DOJINHTV": ("DOJI nữ trang", "DOJI", "Việt Nam", None),
    "BTSJC": ("Bảo Tín SJC", "Bảo Tín Minh Châu", "Việt Nam", None),
    "BT9999NTT": ("Bảo Tín 9999", "Bảo Tín Minh Châu", "Việt Nam", "0.9999"),
    "PQHNVM": ("PNJ Hà Nội", "PNJ", "Hà Nội", None),
    "PQHN24NTT": ("PNJ 24K", "PNJ", "Việt Nam", None),
    "VNGSJC": ("VN Gold SJC", "VN Gold", "Việt Nam", None),
    "VIETTINMSJC": ("Viettin SJC", "Viettin", "Việt Nam", None),
}


def product_id(code: str) -> str:
    return f"{SOURCE_ID}-{code.lower()}"


def parse_prices(raw: bytes) -> list[Observation]:
    try:
        body = json.loads(raw, parse_float=Decimal)
        if body["success"] is not True or not isinstance(body["prices"], dict):
            raise ValueError
        stamp = body["timestamp"]
        if type(stamp) is not int or stamp <= 0:
            raise ValueError
        observed = datetime.fromtimestamp(stamp, UTC)
        quotes = []
        for code, row in body["prices"].items():
            if code not in PRODUCTS:
                continue
            if row["currency"] != "VND":
                raise ValueError
            bid, ask = row["buy"], row["sell"]
            if any(isinstance(v, bool) or not isinstance(v, (int, Decimal)) for v in (bid, ask)):
                raise ValueError
            fingerprint = f"{code}|{stamp}|{Decimal(bid).normalize()}|{Decimal(ask).normalize()}|VND/luong"
            quotes.append(Observation(
                kind="gold", provider_id=SOURCE_ID, product_id=product_id(code), provider_timestamp=observed,
                bid=bid, ask=ask, unit="VND/luong", reference_type="official",
                raw_payload_hash=hashlib.sha256(fingerprint.encode()).hexdigest(),
            ))
        if not quotes:
            raise ValueError
        return quotes
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise SourceUnavailable("provider_schema_changed") from exc


class VangTodayGoldProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.vang_today_enabled:
            raise SourceUnavailable("source_disabled")
        return parse_prices(fetch_vang_today(self.settings.request_timeout_seconds, self.settings.source_allowlist))


def parse_spot(raw: bytes) -> Observation:
    try:
        body = json.loads(raw, parse_float=Decimal)
        if body["success"] is not True or body["type"] != "XAUUSD":
            raise ValueError
        stamp = body["timestamp"]
        if type(stamp) is not int or stamp <= 0:
            raise ValueError
        # In this endpoint buy carries the XAU/USD price and sell is a placeholder.
        value = body["buy"]
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError
        observed = datetime.fromtimestamp(stamp, UTC)
        fingerprint = f"XAUUSD|{stamp}|{Decimal(value).normalize()}|USD/troy_oz"
        return Observation(
            kind="spot", provider_id=SPOT_SOURCE_ID, provider_timestamp=observed,
            value=value, unit="USD/troy_oz", reference_type="official",
            raw_payload_hash=hashlib.sha256(fingerprint.encode()).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise SourceUnavailable("provider_schema_changed") from None


class VangTodaySpotProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.vang_today_enabled:
            raise SourceUnavailable("source_disabled")
        raw = fetch_vang_today(
            self.settings.request_timeout_seconds, self.settings.source_allowlist, xauusd=True
        )
        return [parse_spot(raw)]
