import json
import re

import numpy as np
import pandas as pd
import pytest

from tradebot.ai import review as review_module
from tradebot.ai.base import AIResponseError, QuotaExceededError, Review, ReviewDecision
from tradebot.ai.context import AssetFrames, build_context
from tradebot.ai.prompt import render_prompt
from tradebot.ai.review import UNREVIEWED, review_signal, size_for
from tradebot.ai_eval import SampledSignal, sample_signals
from tradebot.config import AISettings
from tradebot.strategy import LONG

AI = AISettings(provider="cli", filter_model="haiku", decision_model="sonnet",
                daily_call_limit=40, timeout_seconds=60, fallback="veto")


def asset(n: int = 600, seed: int = 0) -> AssetFrames:
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = pd.Series(50_000 + rng.standard_normal(n).cumsum() * 200, index=idx)
    candles = pd.DataFrame({"open": close, "high": close + 100, "low": close - 100, "close": close,
                            "volume": 1000 + rng.random(n) * 100}, index=idx)
    features = pd.DataFrame({"ema_fast": close.ewm(span=50).mean(), "ema_slow": close.ewm(span=200).mean(),
                             "rsi": 55.0, "atr": 300.0, "atr_pct": 300 / close, "bb_width": 0.05}, index=idx)
    regime = pd.Series(1.0, index=idx)
    funding = pd.Series(0.0001, index=pd.date_range("2024-01-01", periods=n * 4, freq="h", tz="UTC"))[::8]
    fear_greed = pd.Series(range(len(pd.date_range("2024-01-01", periods=n // 6 + 2, freq="D"))),
                           index=pd.date_range("2024-01-01", periods=n // 6 + 2, freq="D", tz="UTC"), dtype=float)
    return AssetFrames(candles, features, regime, funding, fear_greed)


def test_context_has_no_dates_prices_or_symbols():
    a = asset()
    ts = a.candles.index[400]
    context = build_context(a, a, ts, ts + pd.Timedelta("4h"), LONG, "ruptura", 0.8)
    text = render_prompt(context)
    assert not re.search(r"20\d\d-\d\d", text), "el prompt no debe contener fechas"
    assert "BTC" not in text and "USDT" not in text
    price = a.candles["close"].iloc[400]
    assert f"{price:.0f}" not in text, "el prompt no debe contener precios absolutos"


def test_context_ignores_future_data():
    a = asset()
    ts = a.candles.index[400]
    decision = ts + pd.Timedelta("4h")
    before = build_context(a, a, ts, decision, LONG, "ruptura", 0.8)
    future = a.candles.copy()
    future.loc[future.index > ts, ["close", "volume"]] *= 3  # todo lo posterior cambia
    funding = a.funding.copy()
    funding[funding.index >= decision] = 0.05
    changed = AssetFrames(future, a.features, a.regime, funding, a.fear_greed)
    assert build_context(changed, changed, ts, decision, LONG, "ruptura", 0.8) == before


def test_prompt_is_valid_json_context():
    a = asset()
    ts = a.candles.index[400]
    context = build_context(a, a, ts, ts + pd.Timedelta("4h"), LONG, "ruptura", 0.8)
    body = render_prompt(context).split("Contexto (JSON):\n", 1)[1].split("\n\nResponde", 1)[0]
    assert json.loads(body) == context


def test_size_never_exceeds_one():
    assert size_for("approve", 5.0) == 1.0
    assert size_for("reduce", 1.0) == 0.9
    assert size_for("reduce", 0.0) == 0.1
    assert size_for("veto", 1.0) == 0.0


def test_sample_is_spread_and_deterministic():
    ts = pd.date_range("2024-01-01", periods=1000, freq="4h", tz="UTC")
    signals = [SampledSignal("X", t, LONG, 1.0, "") for t in ts]
    first, second = sample_signals(signals, 100), sample_signals(signals, 100)
    assert first == second
    assert len(first) == 100
    chosen = sorted(s.ts for s in first)
    assert chosen[0] == ts[0] and chosen[-1] == ts[-1]
    assert [s.ts for s in first] != chosen  # orden aleatorio, no cronológico


class FakeAnalyst:
    def __init__(self, result):
        self.result = result

    def review(self, prompt, model):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def fake_db(monkeypatch):
    saved = []
    state = {"quota": True}
    monkeypatch.setattr(review_module.db, "reserve_ai_call", lambda conn, instance, limit: state["quota"])
    monkeypatch.setattr(review_module.db, "save_ai_review", lambda conn, *args: saved.append(args))
    return saved, state


def test_review_approve(fake_db):
    saved, _ = fake_db
    decision = ReviewDecision(decision="reduce", confidence=0.6, size_multiplier=0.5, reasons=["funding alto"])
    outcome = review_signal(None, FakeAnalyst(Review(decision, "sonnet", 100, 20, 900)), AI, "inst", 1, "prompt")
    assert (outcome.decision, outcome.size_multiplier) == ("reduce", 0.5)
    assert saved[0][3]["decision"] == "reduce"


def test_review_failure_falls_back_to_veto(fake_db):
    saved, _ = fake_db
    outcome = review_signal(None, FakeAnalyst(AIResponseError("json inválido")), AI, "inst", 1, "prompt")
    assert (outcome.decision, outcome.size_multiplier) == (UNREVIEWED, 0.0)
    assert saved[0][4] is None and "json" in saved[0][5]


def test_plan_quota_marks_exhausted(fake_db):
    outcome = review_signal(None, FakeAnalyst(QuotaExceededError("usage limit")), AI, "inst", 1, "prompt")
    assert outcome.quota_exhausted


def test_own_daily_limit_does_not_call_or_save(fake_db):
    saved, state = fake_db
    state["quota"] = False
    outcome = review_signal(None, FakeAnalyst(AssertionError("no debe llamarse")), AI, "inst", 1, "prompt")
    assert outcome.quota_exhausted and saved == []


def test_base_fallback_keeps_full_size(fake_db):
    settings = AISettings(**{**AI.__dict__, "fallback": "base"})
    outcome = review_signal(None, FakeAnalyst(AIResponseError("x")), settings, "inst", 1, "prompt")
    assert outcome.size_multiplier == 1.0


def test_fresh_signals_keep_first_bar_of_each_breakout():
    from tradebot.ai_eval import fresh_signals
    from tradebot.strategy import SHORT

    idx = pd.date_range("2024-01-01", periods=6, freq="4h", tz="UTC")
    signals = pd.DataFrame({"direction": [LONG, LONG, SHORT, LONG]}, index=idx[[0, 1, 2, 4]])
    kept = fresh_signals(signals, pd.Timedelta("4h"))
    assert list(kept.index) == [idx[0], idx[2], idx[4]]


def test_uniform_size_cut_is_not_skill():
    from tradebot.ai_eval import selection_skill

    r = np.array([-1.0, -1.0, 2.0, -1.0])
    assert selection_skill(np.column_stack([r, np.full(4, 0.4)])) == pytest.approx(0)


def test_sizing_winners_up_is_skill():
    from tradebot.ai_eval import selection_skill

    r = np.array([-1.0, -1.0, 2.0, -1.0])
    size = np.array([0.1, 0.1, 0.9, 0.1])
    assert selection_skill(np.column_stack([r, size])) > 0
    assert selection_skill(np.column_stack([r, size[::-1]])) < 0


def test_block_bootstrap_widens_interval_for_correlated_outcomes():
    from tradebot.ai_eval import bootstrap_interval

    # 20 semanas; las 5 señales de cada semana terminan igual: en realidad hay 20 datos, no 100.
    rng = np.random.default_rng(1)
    r = np.repeat(rng.normal(0, 1, 20), 5)
    blocks = np.repeat(np.arange(20), 5)
    naive = bootstrap_interval(r, np.mean, n=2000)
    by_block = bootstrap_interval(r, np.mean, n=2000, blocks=blocks)
    assert (by_block[1] - by_block[0]) > 1.8 * (naive[1] - naive[0])


def test_v2_context_has_no_dates_prices_and_ignores_future():
    from tradebot.ai.context import build_context_v2

    a = asset()
    ts = a.candles.index[400]
    decision = ts + pd.Timedelta("4h")
    before = build_context_v2(a, a, ts, decision, LONG, "ruptura", 0.8)
    text = render_prompt(before, version="v2")
    assert not re.search(r"20\d\d-\d\d", text)
    assert f"{a.candles['close'].iloc[400]:.0f}" not in text
    future = a.candles.copy()
    future.loc[future.index > ts, ["high", "low", "close", "volume"]] *= 3
    changed = AssetFrames(future, a.features, a.regime, a.funding, a.fear_greed)
    assert build_context_v2(changed, changed, ts, decision, LONG, "ruptura", 0.8) == before


def test_score_reply_maps_to_decision_and_size():
    from tradebot.ai.base import parse_decision

    low, mid, high = (parse_decision(f'{{"score": {s}, "reasons": ["x"]}}') for s in (10, 55, 85))
    assert (low.decision, low.size_multiplier, low.score) == ("veto", 0.0, 10)
    assert (mid.decision, mid.size_multiplier, mid.score) == ("reduce", 0.55, 55)
    assert (high.decision, high.size_multiplier) == ("approve", 1.0)
    with pytest.raises(AIResponseError):
        parse_decision('{"score": 140, "reasons": []}')


def test_rank_correlation_detects_ordering():
    from tradebot.ai_eval import rank_correlation

    r = np.array([-1.0, -1.0, 0.5, 3.0])
    assert rank_correlation(np.column_stack([r, [10, 20, 60, 90]])) > 0.9
    assert rank_correlation(np.column_stack([r, [90, 60, 20, 10]])) < -0.9
    assert np.isnan(rank_correlation(np.column_stack([r, [50, 50, 50, 50]])))
