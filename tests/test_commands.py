from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from tradebot.backtest.trend import scale_targets
from tradebot.broker.base import BrokerPosition
from tradebot.live import commands as commands_module
from tradebot.live.commands import Command, CommandProcessor
from tradebot.live.controls import aggressiveness_at, valid_aggressiveness
from tradebot.risk import RiskState
from tradebot.projection import bands

from test_cycle import NOW, SETTINGS, FakeBroker, FakeStore, make_cycle


class FakeQueue:
    def __init__(self, *commands):
        self.conn = None
        self.pending = list(commands)
        self.done: dict[int, tuple[str, str]] = {}

    def claim(self):
        return self.pending.pop(0) if self.pending else None

    def finish(self, command_id, status, result):
        self.done[command_id] = (status, result)


def command(kind, payload, cid=1, age=timedelta(seconds=30)):
    return Command(cid, kind, payload, NOW - age)


def process(*commands, store=None, broker=None):
    store, broker = store or FakeStore(), broker or FakeBroker()
    queue = FakeQueue(*commands)
    CommandProcessor(SETTINGS, queue, lambda: make_cycle(store, broker), now=lambda: NOW).run()
    return queue.done, store, broker


def test_manual_open_uses_its_own_risk_and_stop():
    done, store, broker = process(command("abrir", {"simbolo": "btc", "lado": "short", "riesgo_pct": 0.5, "stop_pct": 2}))
    assert done[1][0] == "hecha"
    [position] = store.open_positions()
    assert position.origin == "manual" and position.side == "short"
    assert position.stop_price == pytest.approx(102.0)          # 2% sobre el precio de entrada
    assert position.qty == pytest.approx(5000 * 0.005 / 2.0)     # 0,5% del capital hasta el stop
    assert position.stop_order_id in broker.stops


@pytest.mark.parametrize("payload, reason", [
    ({"simbolo": "DOGE", "lado": "long", "riesgo_pct": 0.3, "stop_pct": 2}, "moneda no permitida"),
    ({"simbolo": "BTC", "lado": "arriba", "riesgo_pct": 0.3, "stop_pct": 2}, "lado"),
    ({"simbolo": "BTC", "lado": "long", "riesgo_pct": 5, "stop_pct": 2}, "riesgo_pct"),
    ({"simbolo": "BTC", "lado": "long", "riesgo_pct": 0.3}, "stop_pct"),
])
def test_manual_open_rejects_bad_input(payload, reason):
    done, store, broker = process(command("abrir", payload))
    assert done[1][0] == "rechazada" and reason in done[1][1]
    assert broker.live == {}


def test_manual_open_respects_one_position_per_coin_and_kill_switch():
    store = FakeStore()
    store.insert_position(None, "BTC/USDT:USDT", "long", 1.0, 100.0, 97.0, 3.0, 1.0, "s1", 0.0)
    done, _, _ = process(command("abrir", {"simbolo": "BTC", "lado": "long", "riesgo_pct": 0.3, "stop_pct": 2}), store=store)
    assert done[1][0] == "rechazada" and "una por moneda" in done[1][1]

    done, _, broker = process(command("abrir", {"simbolo": "ETH", "lado": "long", "riesgo_pct": 0.3, "stop_pct": 2}),
                              store=FakeStore(RiskState(kill_switch=True, mode="solo_cierre")))
    assert done[1][0] == "rechazada" and broker.live == {}


def test_close_only_works_on_manual_positions():
    store, broker = FakeStore(), FakeBroker()
    bot_id = store.insert_position(None, "ETH/USDT:USDT", "long", 1.0, 100.0, 97.0, 3.0, 1.0, "s1", 0.0)
    broker.live["ETH/USDT:USDT"] = BrokerPosition("ETH/USDT:USDT", "long", 1.0, 100.0)
    done, _, _ = process(command("abrir", {"simbolo": "BTC", "lado": "long", "riesgo_pct": 0.3, "stop_pct": 2}, cid=1),
                         command("cerrar", {"posicion_id": bot_id}, cid=2), store=store, broker=broker)
    assert done[2][0] == "rechazada"
    manual = next(p for p in store.open_positions() if p.origin == "manual")
    done, _, _ = process(command("cerrar", {"posicion_id": manual.id}), store=store, broker=broker)
    assert done[1][0] == "hecha" and store.positions[manual.id]["reason"] == "manual"


def test_old_commands_expire_instead_of_running_late():
    done, store, broker = process(command("abrir", {"simbolo": "BTC", "lado": "long", "riesgo_pct": 0.3, "stop_pct": 2},
                                          age=timedelta(minutes=30)))
    assert done[1][0] == "rechazada" and "expiró" in done[1][1] and broker.live == {}


def test_aggressiveness_command_validates_and_saves(monkeypatch):
    saved = {}
    monkeypatch.setattr(commands_module, "get_aggressiveness", lambda conn, instance: 1.0)
    monkeypatch.setattr(commands_module, "set_aggressiveness", lambda conn, instance, value: saved.update({instance: value}))
    done, _, _ = process(command("agresividad", {"bot": "rupturas", "valor": 1.5}, cid=1),
                         command("agresividad", {"bot": "tendencia", "valor": 1.3}, cid=2),
                         command("agresividad", {"bot": "otro", "valor": 1}, cid=3))
    assert done[1][0] == "hecha" and "0.45%" in done[1][1]
    assert done[2][0] == "rechazada" and done[3][0] == "rechazada"
    assert saved == {SETTINGS.bot.instance: 1.5}


def test_aggressiveness_scales_bot_risk(monkeypatch):
    from tradebot.ai.review import ReviewOutcome
    from tradebot.live import cycle as cycle_module
    from test_cycle import snapshot
    monkeypatch.setattr(cycle_module, "review_signal", lambda *a: ReviewOutcome("approve", 1.0))
    store, broker = FakeStore(), FakeBroker()
    cycle = make_cycle(store, broker)
    cycle.aggressiveness = 2.0
    cycle.run(snapshot())
    [position] = store.open_positions()
    assert position.qty == pytest.approx(10.0)  # el doble de las 5 unidades a agresividad 1
    assert store.positions[position.id]["aggressiveness"] == 2.0


def test_manual_positions_block_their_coin_but_not_the_bot_quota(monkeypatch):
    from tradebot.risk import entry_block_reason
    state = RiskState()
    taken = {"BTC", "ETH", "SOL"}
    assert entry_block_reason(state, taken, "XRP", SETTINGS.risk) is not None       # todas cuentan
    assert entry_block_reason(state, taken, "XRP", SETTINGS.risk, counted=1) is None  # solo 1 del bot
    assert entry_block_reason(state, taken, "BTC", SETTINGS.risk, counted=0) is not None


def test_valid_aggressiveness_steps():
    assert valid_aggressiveness(0.25) and valid_aggressiveness(1.75) and valid_aggressiveness(2)
    assert not valid_aggressiveness(0.1) and not valid_aggressiveness(1.3) and not valid_aggressiveness(2.25)


def test_trend_aggressiveness_keeps_exposure_capped():
    targets = pd.DataFrame({"A": [0.2, 0.5], "B": [-0.2, -0.4]})
    scaled = scale_targets(targets, 2.0)
    np.testing.assert_allclose(scaled.iloc[0], [0.4, -0.4])
    assert scaled.iloc[1].abs().sum() == pytest.approx(1.0)   # 0,9 × 2 = 1,8 → se topa en 1
    np.testing.assert_allclose(scale_targets(targets, 0.5), targets * 0.5)


def test_aggressiveness_applies_from_the_next_daily_close():
    days = pd.date_range("2026-11-10", periods=4, freq="D", tz="UTC")
    changes = [(pd.Timestamp("2026-11-11 12:00", tz="UTC"), 1.5), (pd.Timestamp("2026-11-13 00:00", tz="UTC"), 0.5)]
    # El cierre del 10 es el 11 a las 00:00 (antes del cambio); el del 12 es el 13 a las 00:00 (justo el cambio).
    assert aggressiveness_at(changes, days).tolist() == [1.0, 1.5, 0.5, 0.5]


def test_projection_bands_are_ordered_and_start_at_capital():
    returns = np.random.default_rng(1).normal(0.001, 0.02, 500)
    table = bands(returns, 5000.0, days=60, paths=500)
    assert len(table) == 61 and (table.iloc[0] == 5000.0).all()
    assert (table["p10"] <= table["p50"]).all() and (table["p50"] <= table["p90"]).all()
    assert table["p90"].iloc[-1] - table["p10"].iloc[-1] > table["p90"].iloc[5] - table["p10"].iloc[5]  # se abre con el tiempo
