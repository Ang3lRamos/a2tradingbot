import numpy as np
import pandas as pd
import pytest

from tradebot.backtest.engine import SymbolData, run_backtest
from tradebot.backtest.metrics import buy_and_hold, max_drawdown
from tradebot.config import BacktestSettings, RiskSettings, StrategySettings
from tradebot.features.indicators import atr, compute_features, rsi
from tradebot.strategy import LONG, generate_signals

STRATEGY = StrategySettings(ema_fast=5, ema_slow=10, rsi_period=14, rsi_long_trigger=40, rsi_short_trigger=60, atr_period=14)
RISK = RiskSettings(risk_per_trade=0.005, stop_atr_multiple=1.5, take_profit_r=2.0,
                    max_open_positions=3, max_daily_loss=0.02, max_drawdown=0.10)
NO_COSTS = BacktestSettings(initial_capital=10_000, fee_rate=0.0, slippage=0.0, oos_start="2030-01-01")


def hourly(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")


def symbol_data(bars: list[tuple[float, float, float, float]], signal_at: dict[int, int], atr_value=2.0,
                funding: dict[int, float] | None = None) -> SymbolData:
    o, h, low, c = (np.array(col, dtype=float) for col in zip(*bars))
    n = len(bars)
    signal = np.zeros(n)
    for i, side in signal_at.items():
        signal[i] = side
    rates = np.zeros(n)
    for i, rate in (funding or {}).items():
        rates[i] = rate
    return SymbolData(o, h, low, c, np.full(n, atr_value), signal, np.ones(n), rates)


# --- indicadores ---

def test_rsi_extremes_and_balance():
    assert rsi(pd.Series(np.arange(1.0, 40.0)), 14).iloc[-1] == 100
    assert rsi(pd.Series(np.arange(40.0, 1.0, -1)), 14).iloc[-1] == pytest.approx(0)
    alternating = pd.Series([100.0 + (i % 2) for i in range(200)])
    assert rsi(alternating, 14).iloc[-1] == pytest.approx(50, abs=3)


def test_atr_of_constant_range():
    n = 50
    close = pd.Series(np.full(n, 100.0))
    assert atr(close + 1, close - 1, close, 14).iloc[-1] == pytest.approx(2.0)


def test_features_do_not_look_ahead():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + rng.standard_normal(300).cumsum(), index=hourly(300))
    candles = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1.0})
    full = compute_features(candles, STRATEGY)
    partial = compute_features(candles.iloc[:200], STRATEGY)
    pd.testing.assert_frame_equal(full.iloc[:200], partial)


# --- estrategia ---

def test_long_signal_when_rsi_crosses_up_in_uptrend():
    features = pd.DataFrame({
        "ema_fast": [110.0, 110.0, 110.0], "ema_slow": [100.0, 100.0, 100.0],
        "rsi": [35.0, 38.0, 42.0], "atr": [2.0, 2.0, 2.0],
    }, index=hourly(3))
    signals = generate_signals(features, STRATEGY)
    assert list(signals["direction"]) == [LONG]
    assert signals.index[0] == features.index[2]
    assert signals["score"].iloc[0] == 5.0


def test_no_long_signal_in_downtrend():
    features = pd.DataFrame({
        "ema_fast": [90.0, 90.0], "ema_slow": [100.0, 100.0], "rsi": [38.0, 42.0], "atr": [2.0, 2.0],
    }, index=hourly(2))
    assert generate_signals(features, STRATEGY).empty


# --- motor ---

def test_take_profit_trade():
    # Señal en la vela 0, entrada en la apertura de la 1 (100). Stop 97, take profit 106.
    bars = [(99, 100, 98, 100), (100, 101, 99, 100), (100, 107, 99.5, 106.5)]
    result = run_backtest(hourly(3), {"X": symbol_data(bars, {0: LONG})}, RISK, NO_COSTS)
    trade = result.trades.iloc[0]
    assert (trade["entry"], trade["exit"], trade["exit_reason"]) == (100, 106, "take profit")
    assert trade["qty"] == pytest.approx(10_000 * 0.005 / 3)
    assert trade["r_multiple"] == pytest.approx(2.0)
    assert result.equity.iloc[-1] == pytest.approx(10_100)


def test_stop_wins_when_both_levels_touched():
    bars = [(99, 100, 98, 100), (100, 110, 90, 100)]
    result = run_backtest(hourly(2), {"X": symbol_data(bars, {0: LONG})}, RISK, NO_COSTS)
    trade = result.trades.iloc[0]
    assert (trade["exit"], trade["exit_reason"]) == (97, "stop")
    assert trade["r_multiple"] == pytest.approx(-1.0)


def test_gap_through_stop_exits_at_open():
    bars = [(99, 100, 98, 100), (100, 101, 99, 100), (95, 96, 94, 95)]
    result = run_backtest(hourly(3), {"X": symbol_data(bars, {0: LONG})}, RISK, NO_COSTS)
    trade = result.trades.iloc[0]
    assert (trade["exit"], trade["exit_reason"]) == (95, "stop (gap)")


def test_costs_reduce_pnl():
    bars = [(99, 100, 98, 100), (100, 101, 99, 100), (100, 107, 99.5, 106.5)]
    costs = BacktestSettings(initial_capital=10_000, fee_rate=0.0005, slippage=0.0002, oos_start="2030-01-01")
    trade = run_backtest(hourly(3), {"X": symbol_data(bars, {0: LONG})}, RISK, costs).trades.iloc[0]
    assert trade["entry"] == pytest.approx(100.02)
    assert trade["fees"] > 0
    assert trade["net_pnl"] < trade["gross_pnl"]


def test_long_pays_positive_funding():
    bars = [(99, 100, 98, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 107, 99.5, 106.5)]
    result = run_backtest(hourly(4), {"X": symbol_data(bars, {0: LONG}, funding={2: 0.001})}, RISK, NO_COSTS)
    trade = result.trades.iloc[0]
    assert trade["funding"] == pytest.approx(trade["qty"] * 100 * 0.001)
    assert trade["net_pnl"] == pytest.approx(trade["gross_pnl"] - trade["funding"])


def test_kill_switch_closes_everything_and_stops():
    # Riesgo por operación enorme para cruzar el drawdown máximo en una sola pérdida.
    risk = RiskSettings(risk_per_trade=0.5, stop_atr_multiple=1.5, take_profit_r=2.0,
                        max_open_positions=1, max_daily_loss=1.0, max_drawdown=0.10)
    bars = [(99, 100, 98, 100), (100, 101, 99, 100), (100, 100, 85, 85), (85, 86, 84, 85), (85, 90, 84, 88)]
    data = {"X": symbol_data(bars, {0: LONG, 3: LONG}, atr_value=20)}
    result = run_backtest(hourly(5), data, risk, NO_COSTS)
    assert result.killed_at == hourly(5)[2]
    assert len(result.trades) == 1  # la señal posterior al kill switch se ignora
    assert result.trades.iloc[0]["exit_reason"] == "kill switch"


def test_never_more_positions_than_allowed():
    bars = [(99, 100, 98, 100)] + [(100, 101, 99, 100)] * 5
    risk = RiskSettings(**{**RISK.__dict__, "max_open_positions": 2})
    data = {s: symbol_data(bars, {0: LONG}) for s in ("A", "B", "C")}
    result = run_backtest(hourly(6), data, risk, NO_COSTS)
    assert len(result.trades) == 2  # todas cierran al final del periodo


# --- métricas ---

def test_max_drawdown():
    assert max_drawdown(pd.Series([100.0, 120.0, 90.0, 130.0])) == pytest.approx(-0.25)


def test_buy_and_hold_without_costs():
    equity = buy_and_hold(pd.Series([100.0, 150.0]), NO_COSTS)
    assert equity.iloc[-1] == pytest.approx(15_000)
