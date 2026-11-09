"""Motor de riesgo en vivo: mismas reglas que el backtest, definidas en código.

La IA solo entrega un multiplicador de tamaño <= 1: nunca puede saltarse estos límites.
"""

from dataclasses import dataclass, replace
from datetime import date

from tradebot.config import RiskSettings

OPERATE, CLOSE_ONLY = "operar", "solo_cierre"
REASON_DAILY_LOSS = "perdida_diaria"


@dataclass(frozen=True)
class RiskState:
    mode: str = OPERATE
    mode_reason: str | None = None
    kill_switch: bool = False
    equity_peak: float | None = None
    day_start_equity: float | None = None
    risk_day: date | None = None


@dataclass(frozen=True)
class RiskUpdate:
    state: RiskState
    events: list[str]
    trigger_kill: bool  # recién activado: hay que cerrar todo


def update_risk_state(state: RiskState, equity: float, today: date, risk: RiskSettings) -> RiskUpdate:
    events: list[str] = []
    if state.kill_switch:
        return RiskUpdate(state, events, False)

    if state.risk_day != today:
        state = replace(state, risk_day=today, day_start_equity=equity)
        if state.mode_reason == REASON_DAILY_LOSS:
            state = replace(state, mode=OPERATE, mode_reason=None)
            events.append("nuevo día: termina el modo solo cierre por pérdida diaria")
    peak = max(state.equity_peak or equity, equity)
    state = replace(state, equity_peak=peak)

    if equity < peak * (1 - risk.max_drawdown):
        events.append(f"KILL SWITCH: capital {equity:,.2f} cae más de {risk.max_drawdown:.0%} desde el pico {peak:,.2f}")
        return RiskUpdate(replace(state, kill_switch=True, mode=CLOSE_ONLY, mode_reason="kill_switch"), events, True)

    if state.mode == OPERATE and equity < state.day_start_equity * (1 - risk.max_daily_loss):
        events.append(f"pérdida diaria mayor a {risk.max_daily_loss:.0%}: solo cierre hasta mañana")
        state = replace(state, mode=CLOSE_ONLY, mode_reason=REASON_DAILY_LOSS)
    return RiskUpdate(state, events, False)


def entry_block_reason(state: RiskState, open_symbols: set[str], symbol: str, risk: RiskSettings) -> str | None:
    if state.kill_switch:
        return "kill switch activo"
    if state.mode != OPERATE:
        return f"modo {state.mode} ({state.mode_reason})"
    if symbol in open_symbols:
        return "ya hay una posición en este símbolo"
    if len(open_symbols) >= risk.max_open_positions:
        return f"máximo de {risk.max_open_positions} posiciones abiertas"
    return None


def position_qty(equity: float, price: float, stop_distance: float, risk: RiskSettings, size_multiplier: float = 1.0) -> float:
    """Tamaño por riesgo fijo, con tope de nocional para no pasar de 1x y multiplicador de la IA (<= 1)."""
    if equity <= 0 or price <= 0 or stop_distance <= 0:
        return 0.0
    by_risk = equity * risk.risk_per_trade / stop_distance
    by_leverage = equity / risk.max_open_positions / price
    return min(by_risk, by_leverage) * min(max(size_multiplier, 0.0), 1.0)


def trailed_stop(side: str, entry: float, current_stop: float, close: float, risk_distance: float) -> float | None:
    """Nuevo stop si la operación gana al menos 1R y el stop mejora; None si no cambia. Igual que el backtest."""
    sign = 1 if side == "long" else -1
    if sign * (close - entry) < risk_distance:
        return None
    candidate = close - sign * risk_distance
    improves = candidate > current_stop if side == "long" else candidate < current_stop
    return candidate if improves else None
