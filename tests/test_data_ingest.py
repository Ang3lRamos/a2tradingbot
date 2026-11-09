from datetime import UTC, datetime

import pytest

from tradebot.data.candles import fetch_closed_candles, last_closed_open_ms
from tradebot.data.context import OPEN_INTEREST_MAX_AGE_MS, fetch_funding_rates, fetch_open_interest, parse_fear_greed
from tradebot.data.paginate import paginate, to_datetime, to_ms
from tradebot.db import _context_column
from tradebot.ingest import start_ms

HOUR = 3_600_000
T0 = to_ms(datetime(2024, 1, 1, tzinfo=UTC))


class FakeExchange:
    """Simula los endpoints paginados de ccxt: devuelve hasta `limit` elementos desde `since`."""

    def __init__(self, n_hours: int):
        self.candles = [[T0 + i * HOUR, 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n_hours)]
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls += 1
        return [c for c in self.candles if c[0] >= since][:limit]

    def fetch_funding_rate_history(self, symbol, since, limit):
        rows = [{"timestamp": c[0], "fundingRate": 0.0001} for c in self.candles if c[0] % (8 * HOUR) == 0]
        return [r for r in rows if r["timestamp"] >= since][:limit]

    def fetch_open_interest_history(self, symbol, timeframe, since, limit):
        self.oi_since = since
        rows = [{"timestamp": c[0], "openInterestAmount": 100.0} for c in self.candles]
        return [r for r in rows if r["timestamp"] >= since][:limit]


def flatten(pages):
    return [item for page in pages for item in page]


def test_closed_candles_exclude_the_open_one():
    exchange = FakeExchange(n_hours=2500)
    now = T0 + 2400 * HOUR + 30 * 60_000  # media hora dentro de la vela 2400
    candles = flatten(fetch_closed_candles(exchange, "BTC/USDT:USDT", "1h", T0, now))
    assert len(candles) == 2400
    assert candles[-1][0] == T0 + 2399 * HOUR
    assert exchange.calls == 3  # 1000 + 1000 + 400


def test_candles_resume_without_duplicates():
    exchange = FakeExchange(n_hours=100)
    now = T0 + 100 * HOUR
    first = flatten(fetch_closed_candles(exchange, "X", "1h", T0, T0 + 50 * HOUR))
    resume = start_ms(to_datetime(int(first[-1][0])), HOUR, default_ms=0, forced_ms=None)
    rest = flatten(fetch_closed_candles(exchange, "X", "1h", resume, now))
    timestamps = [c[0] for c in first + rest]
    assert timestamps == sorted(set(timestamps))
    assert len(timestamps) == 100


def test_paginate_stops_when_exchange_ignores_since():
    pages = list(paginate(lambda cursor: [1, 2, 3], ts_of=lambda x: x, since_ms=10, until_ms=100, step_ms=1))
    assert pages == []


def test_last_closed_open_ms():
    assert last_closed_open_ms(T0 + HOUR + 1, "1h") == T0 + HOUR
    assert last_closed_open_ms(T0 + HOUR, "1h") == T0 + HOUR


def test_funding_rates_every_8h():
    exchange = FakeExchange(n_hours=48)
    points = flatten(fetch_funding_rates(exchange, "X", T0, T0 + 48 * HOUR))
    assert [ts for ts, _ in points] == [T0 + i * 8 * HOUR for i in range(6)]
    assert all(value == 0.0001 for _, value in points)


def test_open_interest_is_clamped_to_30_days():
    exchange = FakeExchange(n_hours=60 * 24)
    now = T0 + 60 * 24 * HOUR
    points = flatten(fetch_open_interest(exchange, "X", T0, now))
    assert points[0][0] >= now - OPEN_INTEREST_MAX_AGE_MS
    assert len(points) == OPEN_INTEREST_MAX_AGE_MS // HOUR


def test_parse_fear_greed_sorts_and_filters():
    payload = {"data": [
        {"value": "40", "timestamp": "1704153600"},  # 2024-01-02
        {"value": "55", "timestamp": "1704067200"},  # 2024-01-01
        {"value": "70", "timestamp": "1703980800"},  # 2023-12-31, antes de since
    ]}
    assert parse_fear_greed(payload, since_ms=T0) == [(T0, 55.0), (T0 + 24 * HOUR, 40.0)]


def test_start_ms_priority():
    last = to_datetime(T0)
    assert start_ms(last, HOUR, default_ms=0, forced_ms=123) == 123
    assert start_ms(last, HOUR, default_ms=0, forced_ms=None) == T0 + HOUR
    assert start_ms(None, HOUR, default_ms=7, forced_ms=None) == 7


def test_context_column_whitelist():
    with pytest.raises(ValueError):
        _context_column("funding_rate; drop table candles")
