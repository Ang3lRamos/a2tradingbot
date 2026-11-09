from datetime import date

import pytest

from tradebot.config import RiskSettings
from tradebot.risk import (
    CLOSE_ONLY, OPERATE, RiskState, entry_block_reason, position_qty, trailed_stop, update_risk_state,
)

RISK = RiskSettings(risk_per_trade=0.003, stop_atr_multiple=1.5, take_profit_r=0.0,
                    max_open_positions=3, max_daily_loss=0.02, max_drawdown=0.10)
D1, D2 = date(2026, 11, 9), date(2026, 11, 10)


def test_first_update_sets_peak_and_day():
    update = update_risk_state(RiskState(), 5000, D1, RISK)
    assert (update.state.equity_peak, update.state.day_start_equity, update.state.risk_day) == (5000, 5000, D1)
    assert update.state.mode == OPERATE and not update.trigger_kill


def test_daily_loss_then_reset_next_day():
    state = update_risk_state(RiskState(), 5000, D1, RISK).state
    state = update_risk_state(state, 4890, D1, RISK).state  # -2,2%
    assert state.mode == CLOSE_ONLY
    state = update_risk_state(state, 4890, D2, RISK).state
    assert state.mode == OPERATE and state.day_start_equity == 4890


def test_kill_switch_triggers_once_and_sticks():
    state = update_risk_state(RiskState(), 5000, D1, RISK).state
    state = update_risk_state(state, 5500, D1, RISK).state
    update = update_risk_state(state, 4940, D1, RISK)  # -10,2% desde 5500
    assert update.trigger_kill and update.state.kill_switch
    again = update_risk_state(update.state, 6000, D2, RISK)
    assert again.state.kill_switch and not again.trigger_kill  # solo se libera a mano


def test_entry_blocks():
    ok = RiskState()
    assert entry_block_reason(ok, set(), "BTC", RISK) is None
    assert "ya hay" in entry_block_reason(ok, {"BTC"}, "BTC", RISK)
    assert "máximo" in entry_block_reason(ok, {"A", "B", "C"}, "BTC", RISK)
    assert "kill" in entry_block_reason(RiskState(kill_switch=True), set(), "BTC", RISK)
    assert "solo_cierre" in entry_block_reason(RiskState(mode=CLOSE_ONLY), set(), "BTC", RISK)


def test_position_qty_by_risk_and_cap():
    # 5000 * 0,3% = 15 USDT de riesgo; stop a 1000 → 0,015. Tope 1x: 5000/3/75000 = 0,0222.
    assert position_qty(5000, 75000, 1000, RISK) == pytest.approx(0.015)
    # Stop muy cercano: manda el tope de nocional.
    assert position_qty(5000, 75000, 10, RISK) == pytest.approx(5000 / 3 / 75000)
    # La IA solo reduce.
    assert position_qty(5000, 75000, 1000, RISK, size_multiplier=0.5) == pytest.approx(0.0075)
    assert position_qty(5000, 75000, 1000, RISK, size_multiplier=3.0) == pytest.approx(0.015)
    assert position_qty(0, 75000, 1000, RISK) == 0


def test_trailed_stop_matches_backtest_rule():
    assert trailed_stop("long", 100, 97, 102.9, 3) is None  # todavía no gana 1R
    assert trailed_stop("long", 100, 97, 104, 3) == 101
    assert trailed_stop("long", 100, 101, 103.5, 3) is None  # nunca retrocede
    assert trailed_stop("short", 100, 103, 96, 3) == 99
