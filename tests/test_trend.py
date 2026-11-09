import numpy as np
import pandas as pd
import pytest

from tradebot.backtest.trend import simulate, target_weights
from tradebot.config import BacktestSettings

COSTS = BacktestSettings(initial_capital=1.0, fee_rate=0.0005, slippage=0.0002, oos_start="2030-01-01")
NO_COSTS = BacktestSettings(initial_capital=1.0, fee_rate=0.0, slippage=0.0, oos_start="2030-01-01")


def prices(n=300, seed=0, drift=0.002):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({s: 100 * np.cumprod(1 + rng.normal(drift, 0.03, n)) for s in ("A", "B", "C")}, index=days)


def test_weights_do_not_look_ahead():
    closes = prices()
    changed = closes.copy()
    changed.iloc[200:] *= 3  # cambiar el futuro no puede cambiar los pesos de antes
    pd.testing.assert_frame_equal(target_weights(closes, False).iloc[:200], target_weights(changed, False).iloc[:200])


def test_never_leveraged_and_long_only_has_no_shorts():
    closes = prices(drift=-0.003)
    both, longs = target_weights(closes, False), target_weights(closes, True)
    assert (both.abs().sum(axis=1) <= 1 + 1e-9).all()
    assert (longs >= 0).all().all()
    assert (both < 0).any().any()


def test_profit_comes_from_next_day_not_today():
    days = pd.date_range("2022-01-01", periods=3, freq="D", tz="UTC")
    closes = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=days)
    targets = pd.DataFrame({"A": [0.0, 1.0, 1.0]}, index=days)  # entra al cierre del día 2
    zero = pd.DataFrame({"A": 0.0}, index=days)
    eq = simulate(closes, zero, targets, NO_COSTS, days[0]).equity
    assert eq.iloc[1] == pytest.approx(1.0)   # la subida del día 2 no se gana: aún no estaba dentro
    assert eq.iloc[2] == pytest.approx(1.1)


def test_costs_and_funding_are_charged():
    days = pd.date_range("2022-01-01", periods=3, freq="D", tz="UTC")
    closes = pd.DataFrame({"A": [100.0, 100.0, 100.0]}, index=days)
    targets = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=days)
    funding = pd.DataFrame({"A": [0.0, 0.001, 0.0]}, index=days)  # el largo paga 0,1%
    eq = simulate(closes, funding, targets, COSTS, days[0]).equity
    assert eq.iloc[0] == pytest.approx(1 - 0.0007)
    assert eq.iloc[-1] == pytest.approx((1 - 0.0007) * (1 - 0.001))
