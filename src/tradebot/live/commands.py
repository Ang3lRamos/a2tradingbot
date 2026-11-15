"""Órdenes que llegan desde el dashboard (tabla `commands`, ver sql/007_controls.sql).

El dashboard solo puede dejar órdenes pendientes; aquí se validan con las mismas reglas de riesgo del bot
y se ejecutan con el mismo código (Cycle.execute_entry / Cycle.close_position). Tipos:
- agresividad: {"bot": "rupturas" | "tendencia", "valor": 0.25..2}
- abrir:       {"simbolo": "BTC", "lado": "long" | "short", "riesgo_pct": 0.3, "stop_pct": 2.5}
- cerrar:      {"posicion_id": 12}   (solo operaciones manuales: las del bot siguen su propia regla)

Una orden que espera más de COMMAND_TTL se rechaza: si el bot estuvo apagado, no se ejecuta tarde a otro precio.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from tradebot.config import Settings
from tradebot.exchange import market_symbol
from tradebot.live.controls import get_aggressiveness, set_aggressiveness, valid_aggressiveness
from tradebot.live.cycle import Cycle
from tradebot.risk import CLOSE_ONLY

log = logging.getLogger("tradebot.commands")

COMMAND_TTL = timedelta(minutes=10)
MANUAL_RISK_PCT = (0.05, 2.0)   # % del capital que se arriesga hasta el stop
MANUAL_STOP_PCT = (0.2, 20.0)   # distancia al stop, % del precio


class Rejected(Exception):
    """La orden no pasa las reglas: se marca rechazada con este motivo."""


@dataclass(frozen=True)
class Command:
    id: int
    kind: str
    payload: dict
    created_at: datetime


class CommandQueue:
    def __init__(self, conn):
        self.conn = conn

    def has_pending(self) -> bool:
        return self.conn.execute("select exists (select 1 from commands where status = 'pendiente')").fetchone()[0]

    def claim(self) -> Command | None:
        """Toma la orden pendiente más vieja. `skip locked`: dos procesos nunca toman la misma."""
        row = self.conn.execute(
            "update commands set status = 'ejecutando' where id = ("
            "  select id from commands where status = 'pendiente' order by id limit 1 for update skip locked"
            ") returning id, kind, payload, created_at").fetchone()
        self.conn.commit()
        return Command(row[0], row[1], row[2] or {}, row[3]) if row else None

    def finish(self, command_id: int, status: str, result: str) -> None:
        self.conn.execute("update commands set status = %s, result = %s, processed_at = now() where id = %s",
                          (status, result[:500], command_id))
        self.conn.commit()


def _number(payload: dict, key: str, low: float, high: float) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError):
        raise Rejected(f"falta {key} o no es un número") from None
    if not low <= value <= high:
        raise Rejected(f"{key} debe estar entre {low:g} y {high:g}")
    return value


@dataclass
class CommandProcessor:
    settings: Settings
    queue: CommandQueue
    make_cycle: Callable[[], Cycle]   # el broker se crea solo si hace falta (la agresividad no lo necesita)
    notifier: object = None           # para avisos que no pasan por el ciclo (agresividad)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    _cycle: Cycle | None = None

    @property
    def cycle(self) -> Cycle:
        if self._cycle is None:
            self._cycle = self.make_cycle()
        return self._cycle

    def bots(self) -> dict[str, str]:
        return {"rupturas": self.settings.bot.instance, "tendencia": self.settings.trend.instance}

    def run(self) -> list[str]:
        results = []
        while (command := self.queue.claim()) is not None:
            status, result = self.process(command)
            self.queue.finish(command.id, status, result)
            log.info("orden %d (%s): %s — %s", command.id, command.kind, status, result)
            results.append(f"{command.kind}: {status} — {result}")
        return results

    def process(self, command: Command) -> tuple[str, str]:
        if self.now() - command.created_at > COMMAND_TTL:
            return "rechazada", f"expiró: llevaba más de {COMMAND_TTL.seconds // 60} min esperando (¿bot apagado?)"
        handler = {"agresividad": self.aggressiveness, "abrir": self.open, "cerrar": self.close}.get(command.kind)
        try:
            if handler is None:
                raise Rejected(f"tipo de orden desconocido: {command.kind}")
            return "hecha", handler(command.payload)
        except Rejected as exc:
            return "rechazada", str(exc)
        except Exception as exc:  # noqa: BLE001 - una orden fallida no debe tumbar las siguientes
            log.exception("orden %d falló", command.id)
            return "error", f"{type(exc).__name__}: {exc}"

    # --- tipos de orden ---

    def aggressiveness(self, payload: dict) -> str:
        instance = self.bots().get(str(payload.get("bot")))
        if instance is None:
            raise Rejected("bot desconocido: usa 'rupturas' o 'tendencia'")
        value = _number(payload, "valor", 0.25, 2.0)
        if not valid_aggressiveness(value):
            raise Rejected("la agresividad va en pasos de 0,25")
        conn = self.queue.conn
        before = get_aggressiveness(conn, instance)
        set_aggressiveness(conn, instance, value)
        effect = (f"riesgo por operación {self.settings.risk.risk_per_trade * value:.2%}" if payload["bot"] == "rupturas"
                  else f"exposición objetivo ×{value:g} (tope 100%), desde el próximo rebalanceo")
        message = f"agresividad {payload['bot']}: ×{before:g} → ×{value:g} ({effect})"
        self._notify(message)
        return message

    def open(self, payload: dict) -> str:
        bot = self.settings.bot
        base = str(payload.get("simbolo", "")).upper()
        if base not in bot.bases:
            raise Rejected(f"moneda no permitida: {base or '—'} (solo {', '.join(bot.bases)})")
        side = payload.get("lado")
        if side not in ("long", "short"):
            raise Rejected("lado debe ser long o short")
        if side == "short" and bot.market_type == "spot":
            raise Rejected("en spot no se puede abrir en corto")
        risk_pct = _number(payload, "riesgo_pct", *MANUAL_RISK_PCT)
        stop_pct = _number(payload, "stop_pct", *MANUAL_STOP_PCT)
        symbol = market_symbol(base, bot.quote, bot.market_type)

        cycle = self.cycle
        state, _ = cycle.store.load_state()
        if state.kill_switch or state.mode == CLOSE_ONLY:
            raise Rejected(f"el bot está en {'kill switch' if state.kill_switch else 'solo cierre'}: no se abren operaciones")
        taken = {p.symbol for p in cycle.store.open_positions()} | {p.symbol for p in cycle.broker.positions()}
        if symbol in taken:
            raise Rejected(f"ya hay una posición en {base}: el exchange permite una por moneda")

        reference = cycle.broker.last_price(symbol)
        risk = replace(self.settings.risk, risk_per_trade=risk_pct / 100)
        reason = cycle.execute_entry(symbol, side, reference, reference * stop_pct / 100, risk, origin="manual")
        if reason:
            raise Rejected(reason)
        opened = next(p for p in cycle.store.open_positions() if p.symbol == symbol)
        return f"abierta {side} {opened.qty:g} {base} en {opened.entry_price:g}, stop {opened.stop_price:.2f}"

    def close(self, payload: dict) -> str:
        try:
            position_id = int(payload["posicion_id"])
        except (KeyError, TypeError, ValueError):
            raise Rejected("falta posicion_id") from None
        cycle = self.cycle
        position = next((p for p in cycle.store.open_positions() if p.id == position_id), None)
        if position is None:
            raise Rejected(f"la posición {position_id} no está abierta")
        if position.origin != "manual":
            raise Rejected("solo se cierran a mano las operaciones manuales: las del bot siguen su stop")
        pnl = cycle.close_position(position, "manual")
        return f"cerrada {position.symbol.split('/')[0]} con P&L {pnl:+.2f} USDT"

    def _notify(self, message: str) -> None:
        log.warning(message)
        if self.notifier is not None:
            self.notifier.send("warning", message)
