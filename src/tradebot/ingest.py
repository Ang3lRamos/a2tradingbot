"""Fase 1: ingesta de velas y contexto de mercado hacia Supabase.

Uso:
    python -m tradebot.ingest                 # retoma desde lo último guardado (o 3 años atrás si está vacío)
    python -m tradebot.ingest --years 2       # profundidad inicial si la tabla está vacía
    python -m tradebot.ingest --since 2024-01-01   # vuelve a descargar desde esa fecha (upsert, no duplica)

Es idempotente: se puede correr cada hora o relanzar tras un corte.
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

import ccxt
import psycopg

from tradebot import db
from tradebot.config import load_settings
from tradebot.data.candles import fetch_closed_candles, timeframe_ms
from tradebot.data.context import DAY_MS, HOUR_MS, fetch_fear_greed, fetch_funding_rates, fetch_open_interest
from tradebot.data.paginate import to_datetime, to_ms
from tradebot.features.indicators import compute_features
from tradebot.exchange import create_market_data_exchange, market_symbol

log = logging.getLogger("tradebot.ingest")

EXPECTED_ERRORS = (ccxt.BaseError, psycopg.Error, OSError, ValueError, KeyError)


def start_ms(last: datetime | None, step_ms: int, default_ms: int, forced_ms: int | None) -> int:
    if forced_ms is not None:
        return forced_ms
    if last is not None:
        return to_ms(last) + step_ms
    return default_ms


def ingest_candles(conn, exchange, symbol: str, timeframe: str, since_ms: int, now_ms: int) -> str:
    total = 0
    for page in fetch_closed_candles(exchange, symbol, timeframe, since_ms, now_ms):
        total += db.save_candles(conn, symbol, timeframe, page)
        log.info("  %s %s: %d velas, hasta %s", symbol, timeframe, total, to_datetime(int(page[-1][0])))
    return f"{total} velas nuevas"


def ingest_features(conn, symbol: str, timeframe: str, strategy, step_ms: int) -> str:
    """Recalcula sobre toda la serie (las EMAs dependen de todo el historial) y guarda solo lo nuevo."""
    candles = db.load_candles(conn, symbol, timeframe)
    if candles.empty:
        return "sin velas"
    features = compute_features(candles, strategy)
    last = db.last_features_ts(conn, symbol, timeframe)
    if last is not None:
        features = features[features.index > last]
    return f"{db.save_features(conn, symbol, timeframe, features)} filas nuevas"


def ingest_points(conn, symbol: str, column: str, pages) -> str:
    total = sum(db.save_context(conn, symbol, column, page) for page in pages)
    return f"{total} registros nuevos"


def run_step(conn, name: str, step: Callable[[], str]) -> bool:
    try:
        log.info("%-34s OK    %s", name, step())
        return True
    except EXPECTED_ERRORS as exc:
        conn.rollback()
        log.error("%-34s FALLA %s", name, exc)
        return False


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingesta de velas y contexto de mercado")
    parser.add_argument("--years", type=float, default=3, help="profundidad inicial si no hay datos (default 3)")
    parser.add_argument("--since", type=datetime.fromisoformat, help="forzar descarga desde AAAA-MM-DD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    settings = load_settings()
    bot = settings.bot
    now_ms = int(time.time() * 1000)
    default_ms = now_ms - int(args.years * 365 * DAY_MS)
    forced_ms = to_ms(args.since.replace(tzinfo=args.since.tzinfo or UTC)) if args.since else None

    candles_exchange = create_market_data_exchange(bot)
    # El contexto (funding, open interest) sale siempre de los perpetuos, también si se opera spot.
    perp_exchange = create_market_data_exchange(replace(bot, market_type="swap"))
    step = timeframe_ms(bot.timeframe)
    results = []

    with db.connect() as conn:
        symbols = [market_symbol(base, bot.quote, bot.market_type) for base in bot.bases]
        for base, symbol in zip(bot.bases, symbols):
            perp = market_symbol(base, bot.quote, "swap")

            since = start_ms(db.last_candle_ts(conn, symbol, bot.timeframe), step, default_ms, forced_ms)
            results.append(run_step(conn, f"{symbol} velas {bot.timeframe}",
                lambda: ingest_candles(conn, candles_exchange, symbol, bot.timeframe, since, now_ms)))

            results.append(run_step(conn, f"{symbol} indicadores",
                lambda: ingest_features(conn, symbol, bot.timeframe, settings.strategy, step)))

            since = start_ms(db.last_context_ts(conn, symbol, "funding_rate"), 1, default_ms, forced_ms)
            results.append(run_step(conn, f"{symbol} funding",
                lambda: ingest_points(conn, symbol, "funding_rate",
                                      fetch_funding_rates(perp_exchange, perp, since, now_ms))))

            since = start_ms(db.last_context_ts(conn, symbol, "open_interest"), HOUR_MS, default_ms, forced_ms)
            results.append(run_step(conn, f"{symbol} open interest",
                lambda: ingest_points(conn, symbol, "open_interest",
                                      fetch_open_interest(perp_exchange, perp, since, now_ms))))

        last_fg = db.last_context_ts(conn, symbols[0], "fear_greed")
        since = start_ms(last_fg, DAY_MS, default_ms, forced_ms)
        results.append(run_step(conn, "Fear & Greed",
            lambda: ingest_points_all(conn, symbols, fetch_fear_greed(since, now_ms))))

        for symbol in symbols:
            gaps = db.candle_gaps(conn, symbol, bot.timeframe, step // 1000)
            if gaps:
                log.warning("%s: %d huecos en las velas, el primero entre %s y %s", symbol, len(gaps), *gaps[0])

    return 0 if all(results) else 1


def ingest_points_all(conn, symbols: list[str], points) -> str:
    """Fear & Greed es global: se guarda el mismo valor para cada símbolo."""
    for symbol in symbols:
        db.save_context(conn, symbol, "fear_greed", points)
    return f"{len(points)} días nuevos"


if __name__ == "__main__":
    sys.exit(main())
