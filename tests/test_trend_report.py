import pandas as pd
import pytest

from tradebot.live.trend_report import build_report, max_drawdown

INITIAL = 5000.0


def days(start, values):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D", tz="UTC"), dtype=float)


def report(month, daily, btc=None, replay=None, rebalances=()):
    return build_report(pd.Period(month, freq="M"), daily, daily, btc,
                        daily if replay is None else replay, pd.DatetimeIndex(rebalances, tz="UTC"), INITIAL)


def test_drawdown_counts_initial_capital_as_first_peak():
    assert max_drawdown(days("2026-01-01", [4900, 5100, 4590]), INITIAL) == pytest.approx(4590 / 5100 - 1)
    assert max_drawdown(days("2026-01-01", [4800, 4950]), INITIAL) == pytest.approx(-0.04)


def test_first_month_measures_from_initial_capital_and_btc_from_start_day():
    daily = days("2026-11-08", [4999, 5040, 5100])
    btc = days("2026-11-08", [75000, 73000, 72000])
    r = report("2026-11", daily, btc)
    assert r.first_day == pd.Timestamp("2026-11-08", tz="UTC")
    assert r.month_return == pytest.approx(5100 / INITIAL - 1)
    assert r.total_return == r.month_return
    assert r.btc_month == pytest.approx(72000 / 75000 - 1)
    assert r.days_live == 3


def test_later_month_starts_from_last_close_of_previous_month():
    daily = days("2026-11-29", [5000, 5200, 5300, 5250, 5400])   # 29-nov a 3-dic
    btc = days("2026-11-29", [70000, 71000, 72000, 73000, 74000])
    r = report("2026-12", daily, btc, rebalances=["2026-11-29", "2026-12-02"])
    assert r.month_return == pytest.approx(5400 / 5200 - 1)
    assert r.btc_month == pytest.approx(74000 / 71000 - 1)
    assert r.btc_total == pytest.approx(74000 / 70000 - 1)
    assert r.rebalances == 1


def test_fidelity_flags_a_live_account_that_drifts_from_the_backtest():
    daily = days("2026-11-08", [5000, 5100])
    assert report("2026-11", daily, replay=days("2026-11-08", [5000, 5102])).faithful
    drifted = report("2026-11", daily, replay=days("2026-11-08", [5000, 5300]))
    assert not drifted.faithful
    assert "no coincide" in drifted.card().note


def test_month_without_closed_days_has_no_report():
    assert report("2026-10", days("2026-11-08", [5000])) is None


def test_short_history_is_labeled_as_noise():
    assert "ruido" in report("2026-11", days("2026-11-08", [5000, 5050])).card().note
