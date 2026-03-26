"""Tests for core P&L calculation formulas."""

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def calc_market_value(shares: float, price: float) -> float:
    return shares * price


def calc_profit(shares: float, price: float, cost: float) -> float:
    return shares * (price - cost)


def calc_market_value_sgd(market_value: float, fx_rate: float) -> float:
    return market_value * fx_rate


def calc_profit_sgd(profit: float, fx_rate: float) -> float:
    return profit * fx_rate


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestMarketValue:
    def test_basic(self) -> None:
        assert calc_market_value(10, 200.0) == pytest.approx(2000.0)

    def test_fractional_shares(self) -> None:
        assert calc_market_value(0.5, 100.0) == pytest.approx(50.0)

    def test_zero_shares(self) -> None:
        assert calc_market_value(0, 200.0) == pytest.approx(0.0)


class TestProfit:
    def test_positive_profit(self) -> None:
        # Bought at 150, now at 200 → gain
        assert calc_profit(10, 200.0, 150.0) == pytest.approx(500.0)

    def test_negative_profit(self) -> None:
        # Bought at 200, now at 150 → loss
        assert calc_profit(10, 150.0, 200.0) == pytest.approx(-500.0)

    def test_zero_profit(self) -> None:
        assert calc_profit(10, 150.0, 150.0) == pytest.approx(0.0)

    def test_large_position(self) -> None:
        # 2000 shares, cost 8.68, price 10.0 → profit = 2000*(10-8.68)
        assert calc_profit(2000, 10.0, 8.68) == pytest.approx(2640.0)


class TestFxConversion:
    def test_sgd_fx_rate_is_one(self) -> None:
        """SGD holdings must use fx_rate = 1.0 exactly."""
        fx_rate = 1.0
        mv = calc_market_value(600, 40.0)  # D05.SI
        mv_sgd = calc_market_value_sgd(mv, fx_rate)
        assert mv_sgd == pytest.approx(mv)

    def test_usd_to_sgd(self) -> None:
        fx_rate = 1.35
        profit = calc_profit(10, 200.0, 150.0)  # 500 USD
        profit_sgd = calc_profit_sgd(profit, fx_rate)
        assert profit_sgd == pytest.approx(675.0)

    def test_negative_profit_in_sgd(self) -> None:
        fx_rate = 1.35
        profit = calc_profit(10, 100.0, 150.0)  # -500 USD
        profit_sgd = calc_profit_sgd(profit, fx_rate)
        assert profit_sgd == pytest.approx(-675.0)


class TestEndToEnd:
    """End-to-end calculation for a representative holding."""

    def test_nbis_holding(self) -> None:
        """NBIS: 62 shares @ cost 92.455 USD, price 100 USD, fx 1.35."""
        shares, cost, price, fx = 62, 92.455, 100.0, 1.35

        mv = calc_market_value(shares, price)
        profit = calc_profit(shares, price, cost)
        mv_sgd = calc_market_value_sgd(mv, fx)
        profit_sgd = calc_profit_sgd(profit, fx)

        assert mv == pytest.approx(6200.0)
        assert profit == pytest.approx(62 * (100.0 - 92.455))
        assert mv_sgd == pytest.approx(6200.0 * 1.35)
        assert profit_sgd == pytest.approx(profit * 1.35)

    def test_dbs_holding_sgd(self) -> None:
        """D05.SI: 600 shares @ cost 35.827 SGD, price 40.0, fx 1.0."""
        shares, cost, price, fx = 600, 35.827, 40.0, 1.0

        mv = calc_market_value(shares, price)
        profit = calc_profit(shares, price, cost)
        mv_sgd = calc_market_value_sgd(mv, fx)
        profit_sgd = calc_profit_sgd(profit, fx)

        assert mv == pytest.approx(24000.0)
        assert profit == pytest.approx(600 * (40.0 - 35.827))
        assert mv_sgd == pytest.approx(24000.0)  # no FX conversion
        assert profit_sgd == pytest.approx(profit)
