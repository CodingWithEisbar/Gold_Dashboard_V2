from decimal import Decimal, localcontext

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.gold_math import (
    historical_pnl,
    premium,
    quantity_in_luong,
    scenario,
    validate_quote,
    world_reference,
)

D = Decimal


def test_fixed_loss_and_return():
    result = historical_pnl(D("1"), D("140000000"), D("137000000"))
    assert result.net_pnl_vnd == D("-3000000")
    assert abs(result.net_return_pct - D("-2.142857142857142857")) < D("0.000000000000000001")
    assert result.break_even_exit_bid == D("140000000")


def test_world_reference_no_intermediate_rounding():
    with localcontext() as ctx:
        ctx.prec = 50
        expected = D("4000") * D("26000") * D("37.5") / D("31.1034768")
    assert world_reference(D("4000"), D("26000")) == expected


def test_spread_same_day_and_chi():
    assert historical_pnl(D("1"), D("10"), D("10")).net_pnl_vnd == 0
    assert historical_pnl(D("1"), D("11"), D("10")).net_pnl_vnd < 0
    assert quantity_in_luong(D("1"), "chi") == D("0.1")


@pytest.mark.parametrize("quantity", [D("0"), D("-1"), D("NaN"), D("Infinity"), 1.0])
def test_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        historical_pnl(quantity, D("140000000"), D("137000000"))


@pytest.mark.parametrize("bid,ask", [(D("2"), D("1")), (D("-1"), D("1")), (D("0"), D("NaN"))])
def test_invalid_quote(bid, ask):
    with pytest.raises(ValueError):
        validate_quote(bid, ask)


@pytest.mark.parametrize("spot,fx", [(None, D("26000")), (D("4000"), None), (None, None)])
def test_missing_premium(spot, fx):
    with pytest.raises(ValueError):
        premium(D("137000000"), D("140000000"), spot, fx)


def test_fees_in_return_denominator_and_break_even():
    result = historical_pnl(
        D("2"),
        D("100"),
        D("105"),
        buy_fees_vnd=D("10"),
        sell_fees_vnd=D("3"),
        storage_fees_vnd=D("4"),
        applicable_tax_vnd=D("5"),
    )
    assert result.invested_vnd == D("210")
    assert result.net_pnl_vnd == D("-12")
    assert result.break_even_exit_bid == D("111")
    assert (
        historical_pnl(
            D("2"),
            D("100"),
            result.break_even_exit_bid,
            buy_fees_vnd=D("10"),
            sell_fees_vnd=D("3"),
            storage_fees_vnd=D("4"),
            applicable_tax_vnd=D("5"),
        ).net_pnl_vnd
        == 0
    )


def test_scenario_premium_compression():
    inputs = dict(
        world_reference_now=D("120000000"),
        world_change_pct=D("0"),
        future_spread=D("3000000"),
        quantity=D("1"),
        entry_ask=D("140000000"),
    )
    low = scenario(**inputs, future_premium_pct=D("5"))
    high = scenario(**inputs, future_premium_pct=D("15"))
    assert low["net_pnl_vnd"] < high["net_pnl_vnd"]
    assert low["label"] == "SCENARIO, NOT OBSERVED PRICE"
    with pytest.raises(ValueError):
        scenario(**{**inputs, "future_spread": D("999000000")}, future_premium_pct=D("0"))


@given(
    st.decimals(min_value="0.01", max_value="1000", places=2),
    st.decimals(min_value="1", max_value="1000000000", places=2),
)
def test_equal_prices_have_zero_return(quantity, price):
    result = historical_pnl(quantity, price, price)
    assert result.net_pnl_vnd == 0
    assert result.break_even_exit_bid == price
