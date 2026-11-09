from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from tradebot.ai.context import AssetFrames
from tradebot.ai.review import ReviewOutcome
from tradebot.broker.base import BrokerError, BrokerPosition, Fill
from tradebot.config import load_settings
from tradebot.live import cycle as cycle_module
from tradebot.live.cycle import Cycle, Snapshot, reconcile
from tradebot.live.store import OpenPosition
from tradebot.risk import CLOSE_ONLY, RiskState
from tradebot.strategy import LONG

SETTINGS = load_settings()
BAR = pd.Timestamp("2026-11-09 08:00", tz="UTC")
NOW = datetime(2026, 11, 9, 12, 2, tzinfo=UTC)  # 2 min después del cierre de la vela de las 08:00


class FakeBroker:
    def __init__(self, equity=5000.0):
        self._equity = equity
        self.live: dict[str, BrokerPosition] = {}
        self.stops: dict[str, tuple[str, float]] = {}  # id -> (symbol, price)
        self.fail_stop = False
        self.exit_fills: dict[str, Fill] = {}
        self._next = 0

    def _id(self):
        self._next += 1
        return f"o{self._next}"

    def equity(self):
        return self._equity

    def positions(self):
        return list(self.live.values())

    def round_qty(self, symbol, qty):
        return float(np.floor(qty * 1000) / 1000)

    def min_notional(self, symbol):
        return 5.0

    def market_open(self, symbol, side, qty):
        self.live[symbol] = BrokerPosition(symbol, side, qty, 100.0)
        return Fill(self._id(), 100.0, qty, 0.05)

    def market_close(self, symbol, side, qty):
        self.live.pop(symbol, None)
        return Fill(self._id(), 99.0, qty, 0.05)

    def place_stop(self, symbol, side, qty, stop_price):
        if self.fail_stop:
            raise BrokerError("rechazado")
        order_id = self._id()
        self.stops[order_id] = (symbol, stop_price)
        return order_id

    def cancel_stop(self, symbol, order_id):
        self.stops.pop(order_id, None)

    def open_stop_ids(self, symbol):
        return {i for i, (s, _) in self.stops.items() if s == symbol}

    def exit_fill(self, symbol, side, since_ms):
        return self.exit_fills.get(symbol)


class FakeStore:
    def __init__(self, state=None, last_bar=None):
        self.conn = None
        self.state = state or RiskState()
        self.last_bar = last_bar
        self.positions: dict[int, dict] = {}
        self.signals: set = set()
        self.alerts: list = []
        self.orders: list = []

    def load_state(self):
        return self.state, self.last_bar

    def save_state(self, state):
        self.state = state

    def set_last_cycle_bar(self, ts):
        self.last_bar = ts

    def record_equity(self, ts, equity):
        self.equity_history = getattr(self, "equity_history", []) + [(ts, equity)]

    def open_positions(self):
        return [OpenPosition(i, p["symbol"], p["side"], p["qty"], p["entry"], p["stop"], p["distance"], p["stop_id"],
                             p["opened_at"], p["fees"]) for i, p in self.positions.items() if p["status"] == "open"]

    def insert_position(self, signal_id, symbol, side, qty, entry, stop, distance, size, stop_id, fees):
        pid = len(self.positions) + 1
        self.positions[pid] = dict(symbol=symbol, side=side, qty=qty, entry=entry, stop=stop, distance=distance,
                                   stop_id=stop_id, opened_at=NOW, fees=fees, status="open", size=size)
        return pid

    def update_stop(self, pid, stop, stop_id):
        self.positions[pid].update(stop=stop, stop_id=stop_id)

    def close_position(self, pid, exit_price, pnl, fees, reason):
        self.positions[pid].update(status="closed", exit=exit_price, pnl=pnl, reason=reason)

    def record_order(self, *args):
        self.orders.append(args)

    def new_signal(self, strategy, symbol, timeframe, ts, direction, score, reason):
        key = (symbol, ts)
        if key in self.signals:
            return None
        self.signals.add(key)
        return len(self.signals)

    def alert(self, level, message):
        self.alerts.append((level, message))


def snapshot(signal_symbols=("BTC/USDT:USDT",), close=100.0) -> Snapshot:
    idx = pd.date_range(end=BAR, periods=300, freq="4h", tz="UTC")
    assets, signals = {}, {}
    for symbol in ("BTC/USDT:USDT", "ETH/USDT:USDT"):
        c = pd.Series(close, index=idx)
        candles = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10.0})
        features = pd.DataFrame({"ema_fast": c, "ema_slow": c - 1, "rsi": 60.0, "atr": 2.0, "atr_pct": 0.02,
                                 "bb_width": 0.05}, index=idx)
        assets[symbol] = AssetFrames(candles, features, pd.Series(1.0, index=idx),
                                     pd.Series(0.0001, index=idx), pd.Series(50.0, index=idx.floor("D").unique()))
        rows = {"direction": [LONG], "score": [1.0], "reason": ["ruptura"]} if symbol in signal_symbols else \
            {"direction": [], "score": [], "reason": []}
        signals[symbol] = pd.DataFrame(rows, index=[BAR] if symbol in signal_symbols else pd.DatetimeIndex([], tz="UTC"))
    return Snapshot("donchian-4h-20", "4h", assets, signals)


@pytest.fixture
def approve(monkeypatch):
    calls = []

    def fake_review(conn, analyst, settings, instance, signal_id, prompt):
        calls.append(prompt)
        return ReviewOutcome("approve", 1.0)

    monkeypatch.setattr(cycle_module, "review_signal", fake_review)
    return calls


def make_cycle(store, broker):
    return Cycle(SETTINGS, store, broker, analyst=None, now=lambda: NOW)


def test_signal_opens_position_with_exchange_stop(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    [position] = store.open_positions()
    assert position.side == "long" and position.entry_price == 100.0
    assert position.stop_price == pytest.approx(100 - 1.5 * 2.0)
    assert position.stop_order_id in broker.stops
    # Tamaño: 5000 * 0,3% / 3 = 5 unidades (por debajo del tope 1x de 16,6).
    assert position.qty == pytest.approx(5.0)
    assert len(approve) == 1 and store.last_bar == BAR.to_pydatetime()


def test_same_bar_is_not_processed_twice(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    make_cycle(store, broker).run(snapshot())
    assert len(store.open_positions()) == 1 and len(approve) == 1


def test_veto_does_not_trade(monkeypatch):
    monkeypatch.setattr(cycle_module, "review_signal", lambda *a: ReviewOutcome("veto", 0.0))
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    assert store.open_positions() == [] and broker.live == {}


def test_ai_reduce_scales_size(monkeypatch):
    monkeypatch.setattr(cycle_module, "review_signal", lambda *a: ReviewOutcome("reduce", 0.5))
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    assert store.open_positions()[0].qty == pytest.approx(2.5)


def test_failed_stop_closes_position_immediately(approve):
    store, broker = FakeStore(), FakeBroker()
    broker.fail_stop = True
    make_cycle(store, broker).run(snapshot())
    assert broker.live == {} and store.open_positions() == []
    assert any(level == "critical" for level, _ in store.alerts)


def test_stop_hit_on_exchange_is_recorded(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    broker.live.clear()  # el stop se ejecutó en el exchange
    broker.exit_fills["BTC/USDT:USDT"] = Fill("x", 97.0, 5.0, 0.05)
    make_cycle(store, broker).run(snapshot(signal_symbols=()))
    closed = store.positions[1]
    assert closed["status"] == "closed" and closed["reason"] == "stop"
    assert closed["pnl"] == pytest.approx(5 * (97 - 100) - 0.05 - 0.05)


def test_unknown_exchange_position_forces_close_only(approve):
    store, broker = FakeStore(), FakeBroker()
    broker.live["SOL/USDT:USDT"] = BrokerPosition("SOL/USDT:USDT", "long", 3, 150)
    make_cycle(store, broker).run(snapshot())
    assert store.state.mode == CLOSE_ONLY and store.state.mode_reason == "reconciliacion"
    assert store.open_positions() == []  # no abre nada nuevo


def test_missing_stop_is_replaced(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    broker.stops.clear()
    make_cycle(store, broker).run(snapshot(signal_symbols=()))
    position = store.open_positions()[0]
    assert position.stop_order_id in broker.stops


def test_trailing_moves_stop_on_new_bar(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    old_stop_id = store.open_positions()[0].stop_order_id
    store.last_bar = (BAR - pd.Timedelta("4h")).to_pydatetime()  # simula que llega la vela siguiente
    make_cycle(store, broker).run(snapshot(signal_symbols=(), close=104.0))
    position = store.open_positions()[0]
    assert position.stop_price == pytest.approx(101.0)
    assert old_stop_id not in broker.stops and position.stop_order_id in broker.stops


def test_kill_switch_closes_everything(approve):
    store, broker = FakeStore(), FakeBroker()
    make_cycle(store, broker).run(snapshot())
    broker._equity = 4400.0  # -12% desde el pico de 5000
    make_cycle(store, broker).run(snapshot(signal_symbols=()))
    assert store.state.kill_switch and store.open_positions() == [] and broker.live == {}
    assert broker.stops == {}


def test_stale_data_blocks_entries(approve):
    store, broker = FakeStore(), FakeBroker()
    late = Cycle(SETTINGS, store, broker, analyst=None, now=lambda: NOW + pd.Timedelta("9h"))
    late.run(snapshot())
    assert store.open_positions() == [] and approve == []


def test_reconcile_detects_qty_mismatch():
    db_pos = [OpenPosition(1, "BTC", "long", 1.0, 100, 97, 3, "s", NOW, 0)]
    result = reconcile(db_pos, [BrokerPosition("BTC", "long", 0.5, 100)])
    assert len(result.mismatched) == 1 and not result.matched


def test_empty_account_does_not_call_ai_or_store_zero_equity(approve):
    store, broker = FakeStore(), FakeBroker(equity=0.0)
    make_cycle(store, broker).run(snapshot())
    assert approve == [] and store.open_positions() == []
    assert store.state.equity_peak is None and store.state.mode == "operar"  # no se guarda el modo temporal


def test_alerts_go_to_notifier_and_equity_is_recorded(approve):
    sent = []

    class Notifier:
        def send(self, level, message):
            sent.append(level)

    store, broker = FakeStore(), FakeBroker()
    Cycle(SETTINGS, store, broker, analyst=None, notifier=Notifier(), now=lambda: NOW).run(snapshot())
    assert sent == ["warning"]  # la apertura de la posición; los eventos "info" no se envían
    assert store.equity_history == [(NOW.replace(minute=0), 5000.0)]
