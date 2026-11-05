import hashlib
import json
from decimal import Decimal

from app.config import Settings
from app.providers.base import Observation
from app.providers.safe_http import SourceUnavailable, fetch_spot


def parse_spot(payload: bytes) -> list[Observation]:
    try:
        data = json.loads(
            payload,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
        if (data["status"], data["currency"], data["unit"], data["metal"]) != (
            "success",
            "USD",
            "toz",
            "gold",
        ):
            raise ValueError("unexpected units or status")
        return [
            Observation(
                kind="spot",
                provider_id="metals-dev",
                provider_timestamp=data["timestamp"],
                value=data["rate"]["price"],
                unit="USD/troy_oz",
                reference_type="official",
                raw_payload_hash=hashlib.sha256(payload).hexdigest(),
            )
        ]
    except (ValueError, KeyError, TypeError):
        raise SourceUnavailable("provider_schema_changed") from None


class MetalsDevSpotProvider:
    provider_id = "metals-dev"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[Observation]:
        if not self.settings.metals_license_confirmed or not self.settings.xau_api_key.get_secret_value():
            raise SourceUnavailable("credentials_or_license_missing")
        return parse_spot(
            fetch_spot(
                self.settings.xau_api_key.get_secret_value(),
                self.settings.request_timeout_seconds,
                self.settings.source_allowlist,
            )
        )
