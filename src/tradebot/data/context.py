"""Contexto de mercado: funding rate, open interest y Fear & Greed Index.

Cada fuente se guarda en su propia columna de `market_context` con su frecuencia natural
(funding cada 8 h, open interest cada hora, Fear & Greed diario). Quien la use hace un
"as-of join": toma el último valor conocido antes de cada vela, nunca uno posterior.
"""

import json
import urllib.request
from collections.abc import Iterator

import ccxt

from tradebot.data.paginate import paginate

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
# Binance solo guarda 30 días de historial de open interest.
OPEN_INTEREST_MAX_AGE_MS = 29 * DAY_MS
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit={limit}&format=json"

# (ts_ms, valor)
Point = tuple[int, float]


def fetch_funding_rates(exchange: ccxt.Exchange, symbol: str, since_ms: int, now_ms: int) -> Iterator[list[Point]]:
    pages = paginate(
        fetch_page=lambda cursor: exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000),
        ts_of=lambda item: int(item["timestamp"]),
        since_ms=since_ms,
        until_ms=now_ms,
        step_ms=1,
    )
    for page in pages:
        yield [(int(item["timestamp"]), float(item["fundingRate"])) for item in page]


def fetch_open_interest(exchange: ccxt.Exchange, symbol: str, since_ms: int, now_ms: int) -> Iterator[list[Point]]:
    """Open interest por hora, en contratos. Antes de 30 días atrás no hay datos en Binance."""
    pages = paginate(
        fetch_page=lambda cursor: exchange.fetch_open_interest_history(symbol, "1h", since=cursor, limit=500),
        ts_of=lambda item: int(item["timestamp"]),
        since_ms=max(since_ms, now_ms - OPEN_INTEREST_MAX_AGE_MS),
        until_ms=now_ms,
        step_ms=HOUR_MS,
    )
    for page in pages:
        yield [
            (int(item["timestamp"]), float(item["openInterestAmount"]))
            for item in page
            if item.get("openInterestAmount") is not None
        ]


def fetch_fear_greed(since_ms: int, now_ms: int) -> list[Point]:
    days = max(1, (now_ms - since_ms) // DAY_MS + 2)
    request = urllib.request.Request(FEAR_GREED_URL.format(limit=days), headers={"User-Agent": "tradebot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return parse_fear_greed(payload, since_ms)


def parse_fear_greed(payload: dict, since_ms: int) -> list[Point]:
    points = [(int(item["timestamp"]) * 1000, float(item["value"])) for item in payload.get("data", [])]
    return sorted(point for point in points if point[0] >= since_ms)
