"""Financial source of truth. Decimal only; rounding belongs at the presentation boundary."""

from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from typing import Literal

VERSION = "1.0.0"
GRAMS_PER_LUONG = Decimal("37.5")
GRAMS_PER_TROY_OZ = Decimal("31.1034768")
HUNDRED = Decimal("100")
ZERO = Decimal("0")
MAX_PRICE = Decimal("1000000000000")


def number(
    value: Decimal,
    name: str,
    *,
    positive: bool = False,
    minimum: Decimal = ZERO,
    maximum: Decimal = MAX_PRICE,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name}: cần số Decimal hữu hạn")
    if value < minimum or value > maximum or (positive and value == ZERO):
        raise ValueError(f"{name}: ngoài phạm vi cho phép")
    return value


def quantity_in_luong(quantity: Decimal, unit: Literal["luong", "chi"] = "luong") -> Decimal:
    number(quantity, "quantity", positive=True, maximum=Decimal("100000"))
    if unit not in ("luong", "chi"):
        raise ValueError("unit phải là luong hoặc chi")
    return quantity / Decimal("10") if unit == "chi" else quantity


def validate_quote(bid: Decimal, ask: Decimal) -> None:
    number(bid, "bid")
    number(ask, "ask", positive=True)
    if ask < bid:
        raise ValueError("ask phải lớn hơn hoặc bằng bid")


def world_reference(xau_usd_per_troy_oz: Decimal, usd_vnd: Decimal) -> Decimal:
    number(xau_usd_per_troy_oz, "spot", positive=True)
    number(usd_vnd, "fx", positive=True)
    with localcontext() as ctx:
        ctx.prec = 50
        return xau_usd_per_troy_oz * usd_vnd * GRAMS_PER_LUONG / GRAMS_PER_TROY_OZ


def premium(bid: Decimal, ask: Decimal, spot: Decimal | None, fx: Decimal | None) -> dict:
    validate_quote(bid, ask)
    if spot is None or fx is None:
        raise ValueError("Thiếu spot hoặc FX: không thể công bố premium")
    with localcontext() as ctx:
        ctx.prec = 50
        reference = world_reference(spot, fx)
        absolute = ask - reference
        return {
            "world_reference_vnd_per_luong": reference,
            "premium_absolute_vnd_per_luong": absolute,
            "premium_pct": absolute / reference * HUNDRED,
            "spread_vnd_per_luong": ask - bid,
        }


@dataclass(frozen=True)
class Pnl:
    quantity_luong: Decimal
    invested_vnd: Decimal
    gross_sale_vnd: Decimal
    net_proceeds_vnd: Decimal
    net_pnl_vnd: Decimal
    net_return_pct: Decimal
    break_even_exit_bid: Decimal

    def to_dict(self) -> dict:
        return asdict(self)


def historical_pnl(
    quantity: Decimal,
    entry_ask: Decimal,
    exit_bid: Decimal,
    *,
    unit: Literal["luong", "chi"] = "luong",
    buy_fees_vnd: Decimal = ZERO,
    sell_fees_vnd: Decimal = ZERO,
    storage_fees_vnd: Decimal = ZERO,
    applicable_tax_vnd: Decimal = ZERO,
) -> Pnl:
    number(entry_ask, "entry_ask", positive=True)
    number(exit_bid, "exit_bid")
    for name, value in {
        "buy_fees": buy_fees_vnd,
        "sell_fees": sell_fees_vnd,
        "storage_fees": storage_fees_vnd,
        "tax": applicable_tax_vnd,
    }.items():
        number(value, name)
    with localcontext() as ctx:
        ctx.prec = 50
        qty = quantity_in_luong(quantity, unit)
        invested = qty * entry_ask + buy_fees_vnd
        sale = qty * exit_bid
        exit_costs = sell_fees_vnd + storage_fees_vnd + applicable_tax_vnd
        proceeds = sale - exit_costs
        pnl = proceeds - invested
        return Pnl(
            qty, invested, sale, proceeds, pnl, pnl / invested * HUNDRED, (invested + exit_costs) / qty
        )


def scenario(
    *,
    world_reference_now: Decimal,
    world_change_pct: Decimal,
    future_premium_pct: Decimal,
    future_spread: Decimal,
    quantity: Decimal,
    entry_ask: Decimal,
    **costs,
) -> dict:
    number(world_reference_now, "world_reference_now", positive=True)
    number(world_change_pct, "world_change_pct", minimum=Decimal("-99.99"), maximum=Decimal("1000"))
    number(future_premium_pct, "future_premium_pct", minimum=Decimal("-99.99"), maximum=Decimal("1000"))
    number(future_spread, "future_spread")
    with localcontext() as ctx:
        ctx.prec = 50
        future_world = world_reference_now * (1 + world_change_pct / HUNDRED)
        future_ask = future_world * (1 + future_premium_pct / HUNDRED)
        future_bid = future_ask - future_spread
        validate_quote(future_bid, future_ask)
        result = historical_pnl(quantity, entry_ask, future_bid, **costs).to_dict()
        result.update(
            scenario_future_world_reference=future_world,
            scenario_future_ask=future_ask,
            scenario_future_bid=future_bid,
            reference_type="scenario",
            label="SCENARIO, NOT OBSERVED PRICE",
        )
        return result
