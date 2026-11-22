"""Read a permissioned Gold Futures listing, keeping each delivery month distinct."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import Settings
from app.providers.base import Observation
from app.providers.browser_board import INVESTING_URL, read_board
from app.providers.safe_http import SourceUnavailable

# Scope the timestamp to the quoted instrument; articles also contain <time> tags.
QUOTE_FIELDS = r"""
const field = k => document.querySelector('[data-test="' + k + '"]')?.textContent.trim();
const price = document.querySelector('[data-test="instrument-price-last"]');
const times = price?.parentElement?.parentElement?.querySelectorAll('time[datetime]');
const month = document.body.innerText.match(/(?:^|\n)Month\s*\n([A-Za-z]{3} \d{2})(?:\n|$)/);
const values = [document.querySelector('h1')?.textContent, field('currency-in-label'),
    field('contract_size'), month?.[1], field('settlement_date'), price?.textContent,
    times?.length === 1 ? times[0].dateTime : null];
return [location.href, values.every(Boolean) ? values.map(v => v.trim()).join('\n') : ''];
"""


def parse_future(fields: str, now: datetime) -> list[Observation]:
    try:
        heading, currency, size, month, settlement, raw_price, timestamp = fields.splitlines()
        match = re.fullmatch(r"Gold \(GC([FGHJKMNQUVXZ])([0-9]{1,2})\)", heading)
        if not match or " ".join(currency.split()) != "Currency in USD" or size != "100 Troy Ounces":
            raise ValueError
        expiry = datetime.strptime(settlement, "%m/%d/%Y")
        expected_month = "FGHJKMNQUVXZ"[expiry.month - 1]
        if (
            month != expiry.strftime("%b %y")
            or match[1] != expected_month
            or not str(expiry.year).endswith(match[2])
        ):
            raise ValueError
        if not re.fullmatch(r"(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)(?:\.[0-9]{1,8})?", raw_price):
            raise ValueError
        observed = datetime.fromisoformat(timestamp)
        if observed.tzinfo is None or observed > now + timedelta(minutes=5):
            raise ValueError
        contract = f"GC{expected_month}{expiry.year}"
        price = Decimal(raw_price.replace(",", ""))
        identity = f"{contract}|{observed.astimezone(UTC).isoformat()}|{price.normalize()}"
        return [
            Observation(
                kind="future",
                provider_id="investing-gold",
                contract=contract,
                value=price,
                provider_timestamp=observed,
                unit="USD/troy_oz",
                reference_type="official",
                raw_payload_hash=hashlib.sha256(identity.encode()).hexdigest(),
            )
        ]
    except (ValueError, TypeError):
        raise SourceUnavailable("provider_schema_changed") from None


class InvestingGoldProvider:
    provider_id = "investing-gold"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.investing_enabled:
            raise SourceUnavailable("source_disabled")
        fields = read_board(INVESTING_URL, ("Gold (", "Currency in"), script=QUOTE_FIELDS)
        return parse_future(fields, datetime.now(UTC))
