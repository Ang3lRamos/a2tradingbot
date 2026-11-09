import numpy as np
import pandas as pd
import pytest

from tradebot.backtest.walkforward import chain, equal_risk


def test_chain_compounds_consecutive_pieces():
    days = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    a = pd.Series([100.0, 110.0, 121.0], index=days)                       # +21%
    b = pd.Series([5000.0, 4500.0, 4500.0], index=days + pd.Timedelta(days=3))  # -10%, otro capital
    assert chain([a, b]).iloc[-1] == pytest.approx(1.21 * 0.9)


def test_equal_risk_matches_volatility():
    rng = np.random.default_rng(0)
    days = pd.date_range("2024-01-01", periods=500, freq="D", tz="UTC")
    bot = pd.Series(np.cumprod(1 + rng.normal(0.0005, 0.002, 500)), index=days)
    btc = pd.Series(np.cumprod(1 + rng.normal(0.001, 0.03, 500)), index=days)
    scale, scaled = equal_risk(bot, btc)
    assert scaled.pct_change().dropna().std() == pytest.approx(btc.pct_change().dropna().std(), rel=0.05)
    assert scale > 1
