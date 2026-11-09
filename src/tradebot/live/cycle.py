"""Un ciclo del bot en vivo. Corre cada hora; las decisiones de entrada solo ocurren al cerrar una vela de 4h.

Orden:
1. Reconciliar la base con el exchange (posiciones cerradas por stop, posiciones desconocidas, stops faltantes).
2. Actualizar el estado de riesgo con el capital actual (pérdida diaria, kill switch).
3. Si cerró una vela nueva: mover trailing stops y procesar señales (riesgo → IA → orden + stop en el exchange).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pandas as pd

from tradebot.ai.base import AIAnalyst
from tradebot.ai.context import AssetFrames, build_context
from tradebot.ai.prompt import render_prompt
from tradebot.ai.review import review_signal
from tradebot.broker.base import Broker, BrokerError, BrokerPosition
from tradebot.config import Settings
from tradebot.live.store import LiveStore, OpenPosition
from tradebot.risk import CLOSE_ONLY, entry_block_reason, position_qty, trailed_stop, update_risk_state
from tradebot.strategy import LONG

log = logging.getLogger("tradebot.cycle")


@dataclass(frozen=True)
class Snapshot:
    """Datos de mercado al cierre de la última vela, en la temporalidad de la estrategia."""

    strategy: str
    timeframe: str
    assets: dict[str, AssetFrames]
    signals: dict[str, pd.DataFrame]

    def last_bar(self) -> pd.Timestamp:
        return min(a.candles.index[-1] for a in self.assets.values())


@dataclass(frozen=True)
class Reconciliation:
    closed_externally: list[OpenPosition]
    unknown: list[BrokerPosition]
    mismatched: list[tuple[OpenPosition, BrokerPosition]]
    matched: list[OpenPosition]


def reconcile(db_positions: list[OpenPosition], broker_positions: list[BrokerPosition], tolerance: float = 1e-9) -> Reconciliation:
    on_exchange = {p.symbol: p for p in broker_positions}
    in_db = {p.symbol: p for p in db_positions}
    closed, mismatched, matched = [], [], []
    for symbol, position in in_db.items():
        live = on_exchange.get(symbol)
        if live is None:
            closed.append(position)
        elif live.side != position.side or abs(live.qty - position.qty) > tolerance * max(1, position.qty):
            mismatched.append((position, live))
        else:
            matched.append(position)
    unknown = [p for s, p in on_exchange.items() if s not in in_db]
    return Reconciliation(closed, unknown, mismatched, matched)


def realized_pnl(side: str, qty: float, entry: float, exit_price: float) -> float:
    return (1 if side == "long" else -1) * qty * (exit_price - entry)


@dataclass
class Cycle:
    settings: Settings
    store: LiveStore
    broker: Broker
    analyst: AIAnalyst
    notifier: object = None  # TelegramNotifier o NullNotifier; None = solo log y tabla alerts
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    events: list[str] = field(default_factory=list)

    def _event(self, level: str, message: str) -> None:
        self.events.append(message)
        getattr(log, {"info": "info", "warning": "warning", "critical": "error"}[level])(message)
        if level != "info":
            self.store.alert(level, message)
            if self.notifier is not None:
                self.notifier.send(level, message)

    # 1. Reconciliación

    def reconcile(self) -> bool:
        """Devuelve False si hay un desajuste que obliga a pasar a solo cierre."""
        result = reconcile(self.store.open_positions(), self.broker.positions())
        for position in result.closed_externally:
            since = int(position.opened_at.timestamp() * 1000)
            fill = self.broker.exit_fill(position.symbol, position.side, since)
            if fill:
                pnl = realized_pnl(position.side, position.qty, position.entry_price, fill.price) - position.fees - fill.fee
                self.store.close_position(position.id, fill.price, pnl, position.fees + fill.fee, "stop")
                self._event("warning", f"{position.symbol}: posición cerrada por stop en {fill.price}, P&L {pnl:+.2f}")
            else:
                self.store.close_position(position.id, None, None, position.fees, "desconocido")
                self._event("warning", f"{position.symbol}: la posición ya no existe en el exchange y no se encontró la ejecución")
        problems = [f"{p.symbol}: posición {p.side} {p.qty} en el exchange que la base no conoce" for p in result.unknown]
        problems += [f"{db.symbol}: base {db.side} {db.qty} vs exchange {ex.side} {ex.qty}" for db, ex in result.mismatched]
        for problem in problems:
            self._event("critical", f"Reconciliación: {problem}. Paso a solo cierre; revisar a mano.")
        for position in result.matched:
            self._ensure_stop(position)
        return not problems

    def _ensure_stop(self, position: OpenPosition) -> None:
        if position.stop_order_id and position.stop_order_id in self.broker.open_stop_ids(position.symbol):
            return
        order_id = self.broker.place_stop(position.symbol, position.side, position.qty, position.stop_price)
        self.store.update_stop(position.id, position.stop_price, order_id)
        self._event("warning", f"{position.symbol}: faltaba el stop en el exchange; se volvió a poner en {position.stop_price}")

    # 2. Riesgo

    def update_risk(self, reconciled: bool):
        state, last_bar = self.store.load_state()
        equity = self.broker.equity()
        if equity <= 0:
            # Sin saldo no se actualiza el pico ni el capital del día (quedarían en 0) y no se opera.
            self._event("warning", "la cuenta de futuros no tiene saldo: no se procesan señales")
            return replace(state, mode=CLOSE_ONLY, mode_reason="sin_saldo"), last_bar
        self.store.record_equity(self.now().replace(minute=0, second=0, microsecond=0), equity)
        update = update_risk_state(state, equity, self.now().date(), self.settings.risk)
        state = update.state
        for event in update.events:
            self._event("critical" if update.trigger_kill else "warning", event)
        if not reconciled and state.mode != CLOSE_ONLY:
            state = replace(state, mode=CLOSE_ONLY, mode_reason="reconciliacion")
        self.store.save_state(state)
        if update.trigger_kill:
            self.close_all("kill switch")
        return state, last_bar

    def close_all(self, reason: str) -> None:
        for position in self.store.open_positions():
            if position.stop_order_id:
                self.broker.cancel_stop(position.symbol, position.stop_order_id)
            fill = self.broker.market_close(position.symbol, position.side, position.qty)
            pnl = realized_pnl(position.side, position.qty, position.entry_price, fill.price) - position.fees - fill.fee
            self.store.record_order(position.id, fill.order_id, position.symbol,
                                    "sell" if position.side == "long" else "buy", "market", fill.qty, fill.price, "filled", fill.fee)
            self.store.close_position(position.id, fill.price, pnl, position.fees + fill.fee, reason)
            self._event("critical", f"{position.symbol}: cerrada por {reason} en {fill.price}, P&L {pnl:+.2f}")

    # 3. Vela nueva: trailing y entradas

    def trail_stops(self, snapshot: Snapshot, bar: pd.Timestamp) -> None:
        for position in self.store.open_positions():
            close = float(snapshot.assets[position.symbol].candles.loc[bar, "close"])
            new_stop = trailed_stop(position.side, position.entry_price, position.stop_price, close, position.risk_distance)
            if new_stop is None:
                continue
            # Primero el stop nuevo y después se cancela el viejo: la posición nunca queda sin protección.
            order_id = self.broker.place_stop(position.symbol, position.side, position.qty, new_stop)
            if position.stop_order_id:
                self.broker.cancel_stop(position.symbol, position.stop_order_id)
            self.store.update_stop(position.id, new_stop, order_id)
            self._event("info", f"{position.symbol}: trailing stop {position.stop_price} → {new_stop}")

    def enter(self, snapshot: Snapshot, bar: pd.Timestamp, state) -> None:
        market = next(iter(snapshot.assets.values()))  # el primer símbolo de la config es el referente
        step = pd.Timedelta(snapshot.timeframe)
        for symbol, signals in snapshot.signals.items():
            if bar not in signals.index:
                continue
            row = signals.loc[bar]
            side = "long" if int(row["direction"]) == LONG else "short"
            open_symbols = {p.symbol for p in self.store.open_positions()}
            blocked = entry_block_reason(state, open_symbols, symbol, self.settings.risk)
            signal_id = self.store.new_signal(snapshot.strategy, symbol, snapshot.timeframe, bar.to_pydatetime(),
                                              side, float(row["score"]), row["reason"])
            if signal_id is None:
                continue  # ya procesada en un ciclo anterior
            if blocked:
                self._event("info", f"{symbol}: señal {side} ignorada ({blocked})")
                continue
            asset = snapshot.assets[symbol]
            context = build_context(asset, market, bar, bar + step, int(row["direction"]), row["reason"], float(row["score"]))
            review = review_signal(self.store.conn, self.analyst, self.settings.ai, self.settings.bot.instance,
                                   signal_id, render_prompt(context))
            if review.size_multiplier <= 0:
                # Un veto por error (Claude sin sesión, timeout, tope diario) se avisa: si se repite, el bot no opera.
                self._event("warning" if review.error else "info",
                            f"{symbol}: señal {side} vetada ({review.decision}{', ' + review.error if review.error else ''})")
                continue
            atr = float(asset.features.loc[bar, "atr"])
            self.open_position(symbol, side, asset, bar, atr, review.size_multiplier, signal_id)

    def open_position(self, symbol: str, side: str, asset: AssetFrames, bar: pd.Timestamp, atr: float,
                      size_multiplier: float, signal_id: int) -> None:
        risk = self.settings.risk
        distance = risk.stop_atr_multiple * atr
        reference = float(asset.candles.loc[bar, "close"])
        qty = self.broker.round_qty(symbol, position_qty(self.broker.equity(), reference, distance, risk, size_multiplier))
        if qty <= 0 or qty * reference < self.broker.min_notional(symbol):
            self._event("info", f"{symbol}: tamaño {qty} demasiado chico para el mínimo del exchange; no se opera")
            return
        fill = self.broker.market_open(symbol, side, qty)
        stop = fill.price - distance if side == "long" else fill.price + distance
        try:
            stop_id = self.broker.place_stop(symbol, side, fill.qty, stop)
        except BrokerError as exc:
            # Nunca dejar una posición sin stop: se cierra de inmediato.
            close = self.broker.market_close(symbol, side, fill.qty)
            self._event("critical", f"{symbol}: falló el stop ({exc}); posición cerrada en {close.price}")
            return
        position_id = self.store.insert_position(signal_id, symbol, side, fill.qty, fill.price, stop, distance,
                                                 size_multiplier, stop_id, fill.fee)
        self.store.record_order(position_id, fill.order_id, symbol, "buy" if side == "long" else "sell", "market",
                                fill.qty, fill.price, "filled", fill.fee)
        self.store.record_order(position_id, stop_id, symbol, "sell" if side == "long" else "buy", "stop_market",
                                fill.qty, stop, "open", None)
        self._event("warning", f"{symbol}: abierta {side} {fill.qty} en {fill.price}, stop {stop:.2f} (tamaño IA x{size_multiplier:.2f})")

    # Ciclo completo

    def run(self, snapshot: Snapshot) -> list[str]:
        reconciled = self.reconcile()
        state, last_bar = self.update_risk(reconciled)
        if state.kill_switch:
            self._event("info", "kill switch activo: el bot no opera hasta reanudarlo a mano")
            return self.events
        bar = snapshot.last_bar()
        if last_bar is not None and bar <= pd.Timestamp(last_bar):
            return self.events
        if self.now() - (bar + pd.Timedelta(snapshot.timeframe)) > pd.Timedelta(snapshot.timeframe):
            self._event("warning", f"datos atrasados: la última vela cerrada es {bar}; no se procesan señales")
            return self.events
        self.trail_stops(snapshot, bar)
        if state.mode != CLOSE_ONLY:
            self.enter(snapshot, bar, state)
        self.store.set_last_cycle_bar(bar.to_pydatetime())
        return self.events
