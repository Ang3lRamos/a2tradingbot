"""Interfaz común de broker. El resto del bot solo conoce esto: agregar MT5 u otro exchange
es escribir otra clase que la cumpla."""

from dataclasses import dataclass
from typing import Literal, Protocol

Side = Literal["long", "short"]


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    side: Side
    qty: float
    entry_price: float


@dataclass(frozen=True)
class Fill:
    order_id: str
    price: float
    qty: float
    fee: float


class BrokerError(RuntimeError):
    """El broker rechazó o no pudo completar la operación."""


class Broker(Protocol):
    def equity(self) -> float:
        """Capital total: saldo más ganancias o pérdidas no realizadas."""

    def positions(self) -> list[BrokerPosition]: ...

    def round_qty(self, symbol: str, qty: float) -> float:
        """Redondea hacia abajo al paso del mercado; 0 si no alcanza el mínimo."""

    def min_notional(self, symbol: str) -> float: ...

    def market_open(self, symbol: str, side: Side, qty: float) -> Fill: ...

    def market_close(self, symbol: str, side: Side, qty: float) -> Fill:
        """Cierra (reduce-only) una posición `side`."""

    def place_stop(self, symbol: str, side: Side, qty: float, stop_price: float) -> str:
        """Stop a mercado reduce-only en el exchange para una posición `side`. Devuelve el id."""

    def cancel_stop(self, symbol: str, order_id: str) -> None: ...

    def open_stop_ids(self, symbol: str) -> set[str]: ...

    def exit_fill(self, symbol: str, side: Side, since_ms: int) -> Fill | None:
        """Última ejecución que cerró una posición `side` desde `since_ms` (p. ej. un stop)."""
