"""Simulador vela a vela con las mismas reglas de riesgo que usará el bot en vivo.

Supuestos, todos en contra del bot cuando hay duda:
- La señal se calcula al cierre de la vela t y se entra en la apertura de t+1, con slippage.
- Si en una misma vela se tocan el stop y el take profit, se asume que primero se tocó el stop.
- Si la vela abre más allá del stop (gap), se sale en la apertura, no en el stop.
- Comisión taker en entrada y salida; slippage en entradas y stops (el take profit es orden límite).
- Los perpetuos pagan o cobran funding cada 8 h según la posición abierta.
- Trailing stop (opcional): cuando la operación gana 1R, el stop sigue al cierre a la distancia
  inicial y nunca retrocede. Se ajusta al cierre de la vela y aplica desde la siguiente.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tradebot.config import BacktestSettings, RiskSettings


@dataclass
class Position:
    symbol: str
    side: int
    qty: float
    entry: float
    stop: float
    take_profit: float
    opened_at: pd.Timestamp
    signal_score: float
    fees: float
    risk_distance: float
    funding: float = 0.0

    def trail(self, close: float) -> None:
        if self.side * (close - self.entry) >= self.risk_distance:
            candidate = close - self.side * self.risk_distance
            self.stop = max(self.stop, candidate) if self.side == 1 else min(self.stop, candidate)


@dataclass
class SymbolData:
    """Arreglos alineados al índice común de tiempo. NaN donde no hay vela."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    atr: np.ndarray
    signal: np.ndarray  # +1 long, -1 short, 0 nada (al cierre de la vela)
    score: np.ndarray
    funding: np.ndarray  # tasa de funding cobrada en esa vela, 0 si no hay


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    killed_at: pd.Timestamp | None = None
    events: list[str] = field(default_factory=list)


def _exit_price(position: Position, o: float, h: float, low: float) -> tuple[float, str] | None:
    if position.side == 1:
        if o <= position.stop:
            return o, "stop (gap)"
        if o >= position.take_profit:
            return o, "take profit (gap)"
        if low <= position.stop:
            return position.stop, "stop"
        if h >= position.take_profit:
            return position.take_profit, "take profit"
    else:
        if o >= position.stop:
            return o, "stop (gap)"
        if o <= position.take_profit:
            return o, "take profit (gap)"
        if h >= position.stop:
            return position.stop, "stop"
        if low <= position.take_profit:
            return position.take_profit, "take profit"
    return None


def run_backtest(
    index: pd.DatetimeIndex, data: dict[str, SymbolData], risk: RiskSettings, costs: BacktestSettings,
    trailing_stop: bool = False,
) -> BacktestResult:
    """`risk.take_profit_r <= 0` desactiva el take profit (la salida queda solo en el stop)."""
    cash = costs.initial_capital
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity_curve = np.empty(len(index))
    peak = cash
    day, day_start_equity = None, cash
    entries_blocked_today = False
    killed_at = None
    events: list[str] = []
    last_equity = cash

    def close(position: Position, price: float, ts: pd.Timestamp, reason: str, slipped: bool) -> None:
        nonlocal cash
        if slipped:
            price *= 1 - position.side * costs.slippage
        fee = price * position.qty * costs.fee_rate
        gross = position.side * position.qty * (price - position.entry)
        cash += gross - fee
        risk_amount = abs(position.entry - position.stop) * position.qty
        net = gross - fee - position.fees - position.funding
        trades.append({
            "symbol": position.symbol, "side": "long" if position.side == 1 else "short",
            "opened_at": position.opened_at, "closed_at": ts, "entry": position.entry, "exit": price,
            "qty": position.qty, "gross_pnl": gross, "fees": fee + position.fees, "funding": position.funding,
            "net_pnl": net, "r_multiple": net / risk_amount if risk_amount else 0.0,
            "exit_reason": reason, "signal_score": position.signal_score,
        })
        del positions[position.symbol]

    for i, ts in enumerate(index):
        if killed_at is None:
            if ts.date() != day:
                day, day_start_equity, entries_blocked_today = ts.date(), last_equity, False

            # 1. Entradas pendientes: señal al cierre de i-1, entrada en la apertura de i.
            if i > 0 and not entries_blocked_today:
                for symbol, d in data.items():
                    side = int(d.signal[i - 1])
                    if side == 0 or symbol in positions or len(positions) >= risk.max_open_positions:
                        continue
                    if np.isnan(d.open[i]) or np.isnan(d.atr[i - 1]):
                        continue
                    entry = d.open[i] * (1 + side * costs.slippage)
                    distance = risk.stop_atr_multiple * d.atr[i - 1]
                    # 1x: la suma de nocionales nunca supera el capital.
                    max_qty = last_equity / risk.max_open_positions / entry
                    qty = min(last_equity * risk.risk_per_trade / distance, max_qty)
                    fee = entry * qty * costs.fee_rate
                    cash -= fee
                    take_profit = (entry + side * distance * risk.take_profit_r
                                   if risk.take_profit_r > 0 else side * np.inf)
                    positions[symbol] = Position(
                        symbol, side, qty, entry, stop=entry - side * distance, take_profit=take_profit,
                        opened_at=ts, signal_score=float(d.score[i - 1]), fees=fee, risk_distance=distance,
                    )

            # 2. Funding y salidas dentro de la vela.
            for symbol in list(positions):
                d, position = data[symbol], positions[symbol]
                if np.isnan(d.open[i]):
                    continue
                if d.funding[i] and position.opened_at < ts:
                    payment = position.side * position.qty * d.open[i] * d.funding[i]
                    cash -= payment
                    position.funding += payment
                hit = _exit_price(position, d.open[i], d.high[i], d.low[i])
                if hit:
                    price, reason = hit
                    close(position, price, ts, reason, slipped=reason.startswith("stop"))
                elif trailing_stop and not np.isnan(d.close[i]):
                    position.trail(d.close[i])

        # 3. Valor de la cuenta al cierre de la vela.
        unrealized = sum(
            p.side * p.qty * (data[s].close[i] - p.entry)
            for s, p in positions.items() if not np.isnan(data[s].close[i])
        )
        last_equity = cash + unrealized
        peak = max(peak, last_equity)

        # 4. Límites de riesgo.
        if killed_at is None and last_equity < peak * (1 - risk.max_drawdown):
            for symbol in list(positions):
                close(positions[symbol], data[symbol].close[i], ts, "kill switch", slipped=True)
            last_equity = cash
            killed_at = ts
            events.append(f"{ts}: kill switch por drawdown de {risk.max_drawdown:.0%}; el bot se detiene")
        elif killed_at is None and not entries_blocked_today and last_equity < day_start_equity * (1 - risk.max_daily_loss):
            entries_blocked_today = True
            events.append(f"{ts}: pérdida diaria de {risk.max_daily_loss:.0%}; solo cierre hasta mañana")

        equity_curve[i] = last_equity

    # Al final del periodo se cierran las posiciones abiertas al último precio.
    for symbol in list(positions):
        close(positions[symbol], data[symbol].close[-1], index[-1], "fin del periodo", slipped=True)
    equity_curve[-1] = cash

    return BacktestResult(pd.Series(equity_curve, index=index, name="equity"), pd.DataFrame(trades), killed_at, events)
