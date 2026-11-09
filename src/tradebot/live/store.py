"""Persistencia del bot en vivo: estado de riesgo, posiciones, órdenes, señales y alertas."""

from dataclasses import dataclass
from datetime import datetime

import psycopg

from tradebot.risk import RiskState


@dataclass(frozen=True)
class OpenPosition:
    id: int
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float
    risk_distance: float
    stop_order_id: str | None
    opened_at: datetime
    fees: float


class LiveStore:
    def __init__(self, conn: psycopg.Connection, instance: str):
        self.conn = conn
        self.instance = instance

    def _commit(self, query: str, params: tuple):
        result = self.conn.execute(query, params)
        self.conn.commit()
        return result

    # --- estado ---

    def load_state(self) -> tuple[RiskState, datetime | None]:
        self._commit("insert into bot_state (instance) values (%s) on conflict do nothing", (self.instance,))
        row = self.conn.execute(
            "select mode, mode_reason, kill_switch, equity_peak, day_start_equity, risk_day, last_cycle_bar "
            "from bot_state where instance = %s", (self.instance,)).fetchone()
        mode, reason, kill, peak, day_start, day, last_bar = row
        state = RiskState(mode, reason, kill, float(peak) if peak is not None else None,
                          float(day_start) if day_start is not None else None, day)
        return state, last_bar

    def save_state(self, state: RiskState) -> None:
        self._commit(
            "update bot_state set mode = %s, mode_reason = %s, kill_switch = %s, equity_peak = %s, "
            "day_start_equity = %s, risk_day = %s, last_heartbeat = now() where instance = %s",
            (state.mode, state.mode_reason, state.kill_switch, state.equity_peak, state.day_start_equity,
             state.risk_day, self.instance))

    def set_last_cycle_bar(self, ts: datetime) -> None:
        self._commit("update bot_state set last_cycle_bar = %s where instance = %s", (ts, self.instance))

    def resume(self) -> None:
        """Reanudar a mano después de revisar: quita kill switch y modo solo cierre; el pico se reinicia."""
        self._commit("update bot_state set kill_switch = false, mode = 'operar', mode_reason = null, "
                     "equity_peak = null where instance = %s", (self.instance,))

    # --- posiciones y órdenes ---

    def open_positions(self) -> list[OpenPosition]:
        rows = self.conn.execute(
            "select id, symbol, side, qty, entry_price, stop_price, risk_distance, stop_order_id, opened_at, fees "
            "from positions where instance = %s and status = 'open' order by opened_at", (self.instance,)).fetchall()
        return [OpenPosition(r[0], r[1], r[2], float(r[3]), float(r[4]), float(r[5]), float(r[6] or 0), r[7], r[8],
                             float(r[9])) for r in rows]

    def insert_position(self, signal_id: int | None, symbol: str, side: str, qty: float, entry: float, stop: float,
                        risk_distance: float, size_multiplier: float, stop_order_id: str, fees: float) -> int:
        return self._commit(
            "insert into positions (instance, signal_id, symbol, side, qty, entry_price, stop_price, risk_distance, "
            "size_multiplier, stop_order_id, fees) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
            (self.instance, signal_id, symbol, side, qty, entry, stop, risk_distance, size_multiplier,
             stop_order_id, fees)).fetchone()[0]

    def update_stop(self, position_id: int, stop: float, stop_order_id: str) -> None:
        self._commit("update positions set stop_price = %s, stop_order_id = %s where id = %s",
                     (stop, stop_order_id, position_id))

    def close_position(self, position_id: int, exit_price: float | None, pnl: float | None, fees: float,
                       reason: str) -> None:
        self._commit(
            "update positions set status = 'closed', exit_price = %s, pnl = %s, fees = %s, exit_reason = %s, "
            "closed_at = now() where id = %s", (exit_price, pnl, fees, reason, position_id))

    def record_order(self, position_id: int | None, order_id: str, symbol: str, side: str, order_type: str,
                     qty: float, price: float | None, status: str, fee: float | None) -> None:
        self._commit(
            "insert into orders (instance, position_id, exchange_order_id, symbol, side, order_type, qty, price, "
            "status, fee) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (exchange_order_id) do update set status = excluded.status, updated_at = now()",
            (self.instance, position_id, order_id, symbol, side, order_type, qty, price, status, fee))

    def record_equity(self, ts: datetime, equity: float) -> None:
        self._commit("insert into equity_snapshots (instance, ts, equity) values (%s, %s, %s) "
                     "on conflict (instance, ts) do update set equity = excluded.equity", (self.instance, ts, equity))

    # --- señales y alertas ---

    def new_signal(self, strategy: str, symbol: str, timeframe: str, ts: datetime, direction: str, score: float,
                   reason: str) -> int | None:
        """Registra la señal y devuelve su id; None si ya estaba (otro ciclo ya la procesó)."""
        row = self._commit(
            "insert into signals (instance, strategy, symbol, timeframe, ts, direction, score, reason) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing returning id",
            (self.instance, strategy, symbol, timeframe, ts, direction, score, reason)).fetchone()
        return row[0] if row else None

    def alert(self, level: str, message: str) -> None:
        self._commit("insert into alerts (instance, level, message) values (%s, %s, %s)",
                     (self.instance, level, message))
