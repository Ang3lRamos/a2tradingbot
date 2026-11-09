import ccxt

from tradebot.broker.ccxt_broker import CCXTBroker


class FakeExchange:
    isSandboxModeEnabled = True
    options = {}

    def __init__(self, trades_error=False):
        self.trades_error = trades_error

    def load_markets(self):
        pass

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        return {"id": "1", "symbol": symbol, "average": None, "price": None, "filled": amount}

    def fetch_my_trades(self, symbol, params=None):
        if self.trades_error:
            raise ccxt.NotSupported("no disponible")
        return [{"order": "1", "amount": 0.5, "price": 100.0, "fee": {"cost": 0.02}},
                {"order": "1", "amount": 0.5, "price": 102.0, "fee": {"cost": 0.03}},
                {"order": "2", "amount": 9.0, "price": 1.0, "fee": {"cost": 9.0}}]


def test_fill_reads_price_and_fee_from_trades():
    fill = CCXTBroker(FakeExchange(), "USDT").market_open("X", "long", 1.0)
    assert (fill.price, fill.qty, round(fill.fee, 6)) == (101.0, 1.0, 0.05)


def test_executed_order_never_raises_when_details_fail():
    # La orden ya se ejecutó: si la consulta de detalles falla, se reporta igual (sin comisión).
    fill = CCXTBroker(FakeExchange(trades_error=True), "USDT").market_close("X", "long", 1.0)
    assert fill.order_id == "1" and fill.fee == 0.0
