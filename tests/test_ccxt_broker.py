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


def test_notifier_disabled_without_credentials(monkeypatch):
    from tradebot import notify

    monkeypatch.setattr(notify, "load_dotenv", lambda: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert isinstance(notify.create_notifier(), notify.NullNotifier)


def test_notifier_failure_does_not_raise(monkeypatch):
    import urllib.request

    from tradebot.notify import TelegramNotifier

    def boom(*args, **kwargs):
        raise OSError("sin red")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert TelegramNotifier("token", "chat").send("critical", "prueba") is False


def test_alert_renders_html_table_and_escapes_text():
    from datetime import UTC, datetime

    from tradebot.notify import Card, render

    now = datetime(2026, 11, 9, 14, 2, tzinfo=UTC)
    text = render("warning", "x", Card("🟢", "BTC LONG abierto", (("Entrada", "97,450.00"), ("Stop", "95,120.00"))),
                  "binance-perp-v1", now)
    assert "<b>BTC LONG abierto</b>" in text
    assert "<pre>Entrada  97,450.00\nStop     95,120.00</pre>" in text
    assert "binance-perp-v1 · 09 nov 14:02 UTC" in text
    plain = render("critical", "base <caída> & reintento", None, "", now)
    assert plain.startswith("🚨 <b>Crítico</b>") and "base &lt;caída&gt; &amp; reintento" in plain
