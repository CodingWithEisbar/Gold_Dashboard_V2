import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

PLAIN_DECIMAL = re.compile(r"-?\d{1,13}(?:\.\d{1,8})?\Z")


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Ngày phải có định dạng YYYY-MM-DD")
    return date.fromisoformat(value)


def decimal_string(value):
    if not isinstance(value, str) or not PLAIN_DECIMAL.fullmatch(value):
        raise ValueError("Gửi số tài chính dưới dạng chuỗi thập phân (tối đa 8 số lẻ)")
    return Decimal(value)


Amount = Annotated[Decimal, BeforeValidator(decimal_string), Field(ge=0, le=Decimal("1000000000000"))]
PositiveAmount = Annotated[Decimal, BeforeValidator(decimal_string), Field(gt=0, le=Decimal("1000000000000"))]
Quantity = Annotated[Decimal, BeforeValidator(decimal_string), Field(gt=0, le=Decimal("100000"))]
Change = Annotated[Decimal, BeforeValidator(decimal_string), Field(ge=Decimal("-99.99"), le=Decimal("1000"))]
ProductId = Annotated[str, Field(pattern=r"^[a-z0-9-]{1,64}$")]
IsoDate = Annotated[date, BeforeValidator(iso_date)]


class Costs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Quantity
    unit: Literal["luong", "chi"] = "luong"
    buy_fees_vnd: Amount = Decimal("0")
    sell_fees_vnd: Amount = Decimal("0")
    storage_fees_vnd: Amount = Decimal("0")
    applicable_tax_vnd: Amount = Decimal("0")


class HistoricalRequest(Costs):
    product_id: ProductId
    entry_date: IsoDate
    exit_date: IsoDate | None = None
    manual_entry_ask: PositiveAmount | None = None
    include_path: bool = False

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.exit_date and (
            self.exit_date < self.entry_date or (self.exit_date - self.entry_date).days > 3650
        ):
            raise ValueError("Ngày bán phải sau ngày mua; tối đa 10 năm")
        return self


class ScenarioRequest(Costs):
    entry_ask: PositiveAmount
    world_reference_now: PositiveAmount
    world_change_pct: Change
    future_premium_pct: Change
    future_spread: Amount
