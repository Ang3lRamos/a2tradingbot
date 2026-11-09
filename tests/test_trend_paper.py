import numpy as np
import pandas as pd
import pytest

from tradebot.backtest.trend import simulate, target_weights
from tradebot.config import BacktestSettings
from tradebot.live.trend_paper import Account, pending_days, step_day

COSTS = BacktestSettings(initial_capital=5000.0, fee_rate=0.0005, slippage=0.0002, oos_start="2030-01-01")


def market(n=400, seed=3):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    closes = pd.DataFrame({s: 100 * np.cumprod(1 + rng.normal(0.001, 0.04, n)) for s in ("A", "B", "C")}, index=days)
    funding = pd.DataFrame(rng.normal(0.0001, 0.0003, (n, 3)), index=days, columns=closes.columns)
    return closes, funding


def test_live_steps_match_backtest_simulation():
    closes, funding = market()
    targets = target_weights(closes, long_only=False)
    start = closes.index[150]
    expected = simulate(closes, funding, targets, COSTS, start).equity

    account, equity = Account(COSTS.initial_capital), []
    for i in range(150, len(closes)):
        prev = closes.iloc[i - 1] if i > 150 else None
        value, _ = step_day(account, closes.iloc[i], prev, funding.iloc[i], targets.iloc[i], COSTS)
        equity.append(value)
    np.testing.assert_allclose(equity, expected.to_numpy(), rtol=2e-3)


def test_first_run_starts_today_and_catch_up_processes_missed_days():
    closes, _ = market(n=10)
    assert pending_days(closes, None) == [closes.index[-1]]
    assert pending_days(closes, closes.index[6].date()) == list(closes.index[7:])
    assert pending_days(closes, closes.index[-1].date()) == []


def test_small_changes_inside_band_do_not_trade():
    close = pd.Series({"A": 100.0})
    account = Account(4000.0, {"A": 10.0})  # 1000 en A sobre un capital de 5000 = 20%
    _, trades = step_day(account, close, None, pd.Series({"A": 0.0}), pd.Series({"A": 0.23}), COSTS)
    assert trades == []
    _, trades = step_day(account, close, None, pd.Series({"A": 0.0}), pd.Series({"A": -0.30}), COSTS)
    assert len(trades) == 1 and trades[0].qty == pytest.approx(-0.5 * 5000 / 100)
