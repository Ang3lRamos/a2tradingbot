"""Broker de futuros perpetuos vía ccxt (Binance Demo Trading o testnet de Bybit).

Supone modo de posición one-way (una posición por símbolo). Los stops son órdenes
condicionales en el exchange: protegen la posición aunque el bot esté caído.
"""

import ccxt

from tradebot.broker.base import BrokerError, BrokerPosition, Fill, Side
from tradebot.exchange import is_paper

CLOSE_SIDE = {"long": "sell", "short": "buy"}
OPEN_SIDE = {"long": "buy", "short": "sell"}


class CCXTBroker:
    def __init__(self, exchange: ccxt.Exchange, quote: str):
        if not is_paper(exchange):
            raise BrokerError("el broker solo opera en testnet o demo en esta etapa del proyecto")
        self.exchange = exchange
        self.quote = quote
        exchange.load_markets()

    def equity(self) -> float:
        info = self.exchange.fetch_balance()["info"]
        # totalMarginBalance = saldo + P&L no realizado (Binance). Si no existe, se usa el total del quote.
        if "totalMarginBalance" in info:
            return float(info["totalMarginBalance"])
        return float(self.exchange.fetch_balance()["total"].get(self.quote) or 0)

    def positions(self) -> list[BrokerPosition]:
        result = []
        for p in self.exchange.fetch_positions():
            contracts = float(p.get("contracts") or 0)
            if contracts > 0:
                result.append(BrokerPosition(p["symbol"], p["side"], contracts, float(p["entryPrice"])))
        return result

    def round_qty(self, symbol: str, qty: float) -> float:
        market = self.exchange.market(symbol)
        try:
            rounded = float(self.exchange.amount_to_precision(symbol, qty))
        except ccxt.InvalidOrder:
            return 0.0
        minimum = market["limits"]["amount"]["min"] or 0
        return rounded if rounded >= minimum else 0.0

    def min_notional(self, symbol: str) -> float:
        return float(self.exchange.market(symbol)["limits"]["cost"]["min"] or 0)

    def _fill(self, order: dict, qty: float) -> Fill:
        """Datos de una orden YA ejecutada. Nunca lanza: si una consulta falla, se usa lo que haya."""
        price = order.get("average") or order.get("price")
        fee = 0.0
        try:
            # La respuesta de una orden a mercado no trae la comisión ni siempre el precio: están en sus ejecuciones.
            trades = [t for t in self.exchange.fetch_my_trades(order["symbol"], params={"orderId": order["id"]})
                      if str(t.get("order")) == str(order["id"])]
            if trades:
                filled = sum(float(t["amount"]) for t in trades)
                price = price or sum(float(t["price"]) * float(t["amount"]) for t in trades) / filled
                fee = sum(float((t.get("fee") or {}).get("cost") or 0) for t in trades)
        except ccxt.BaseError:
            pass
        return Fill(str(order["id"]), float(price or 0), float(order.get("filled") or qty), fee)

    def market_open(self, symbol: str, side: Side, qty: float) -> Fill:
        try:
            order = self.exchange.create_order(symbol, "market", OPEN_SIDE[side], qty)
        except ccxt.BaseError as exc:
            raise BrokerError(f"no se pudo abrir {side} {qty} {symbol}: {exc}") from exc
        return self._fill(order, qty)

    def market_close(self, symbol: str, side: Side, qty: float) -> Fill:
        try:
            order = self.exchange.create_order(symbol, "market", CLOSE_SIDE[side], qty, None, {"reduceOnly": True})
        except ccxt.BaseError as exc:
            raise BrokerError(f"no se pudo cerrar {side} {qty} {symbol}: {exc}") from exc
        return self._fill(order, qty)

    def place_stop(self, symbol: str, side: Side, qty: float, stop_price: float) -> str:
        price = float(self.exchange.price_to_precision(symbol, stop_price))
        try:
            order = self.exchange.create_order(symbol, "market", CLOSE_SIDE[side], qty, None,
                                               {"stopLossPrice": price, "reduceOnly": True})
        except ccxt.BaseError as exc:
            raise BrokerError(f"no se pudo poner el stop de {symbol} en {price}: {exc}") from exc
        return str(order["id"])

    def cancel_stop(self, symbol: str, order_id: str) -> None:
        try:
            self.exchange.cancel_order(order_id, symbol, {"trigger": True})
        except ccxt.OrderNotFound:
            pass  # ya se ejecutó o ya no existe

    def open_stop_ids(self, symbol: str) -> set[str]:
        return {str(o["id"]) for o in self.exchange.fetch_open_orders(symbol, params={"trigger": True})}

    def exit_fill(self, symbol: str, side: Side, since_ms: int) -> Fill | None:
        trades = [t for t in self.exchange.fetch_my_trades(symbol, since=since_ms) if t["side"] == CLOSE_SIDE[side]]
        if not trades:
            return None
        qty = sum(float(t["amount"]) for t in trades)
        price = sum(float(t["price"]) * float(t["amount"]) for t in trades) / qty
        fee = sum(float((t.get("fee") or {}).get("cost") or 0) for t in trades)
        return Fill(str(trades[-1]["order"]), price, qty, fee)
