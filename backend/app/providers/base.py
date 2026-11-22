from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.gold_math import number, validate_quote

SAMPLE_LABEL = "SAMPLE DATA — NOT REAL MARKET DATA"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["gold", "spot", "fx", "future"]
    provider_id: str
    product_id: str | None = None
    contract: str | None = Field(default=None, pattern=r"^GC[FGHJKMNQUVXZ][0-9]{4}$")
    time_basis: Literal["provider", "board_observation"] = "provider"
    provider_timestamp: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    value: Decimal | None = None
    unit: Literal["VND/luong", "USD/troy_oz", "VND/USD"]
    reference_type: Literal["manual", "official", "sample"]
    raw_payload_hash: str

    @field_validator("provider_timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp cần timezone")
        return value

    @model_validator(mode="after")
    def coherent(self):
        expected = {"gold": "VND/luong", "spot": "USD/troy_oz", "fx": "VND/USD", "future": "USD/troy_oz"}
        if (self.kind == "future") != (self.contract is not None):
            raise ValueError("Giá kỳ hạn cần mã hợp đồng GC + tháng + năm bốn chữ số")
        if (self.provider_id == "investing-gold") != (self.kind == "future"):
            raise ValueError("Nguồn Investing Gold chỉ nhận hợp đồng kỳ hạn")
        if self.unit != expected[self.kind]:
            raise ValueError("Sai đơn vị")
        if self.kind == "gold":
            validate_quote(self.bid, self.ask)
            if not self.product_id or self.value is not None:
                raise ValueError("Gold cần product_id và bid/ask")
        else:
            number(self.value, "value", positive=True)
            if self.product_id is not None or self.bid is not None or self.ask is not None:
                raise ValueError("Spot/FX chỉ có value")
        for value in (self.bid, self.ask, self.value):
            if value is not None and value.as_tuple().exponent < -8:
                raise ValueError("Tối đa 8 chữ số thập phân")
        return self


class GoldPriceProvider(Protocol):
    provider_id: str

    def fetch(self) -> list[Observation]: ...


class SpotGoldProvider(Protocol):
    provider_id: str

    def fetch(self) -> list[Observation]: ...


class FxRateProvider(Protocol):
    provider_id: str

    def fetch(self) -> list[Observation]: ...
