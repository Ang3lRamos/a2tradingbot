"""Chequeo de la Fase 0: confirma que Claude, el exchange en testnet y Supabase responden.

Uso: python -m tradebot.check
"""

import logging
import sys
from collections.abc import Callable

import ccxt
import psycopg

from tradebot.ai import AIResponseError, QuotaExceededError, create_analyst
from tradebot.config import Settings, load_database_url, load_exchange_credentials, load_settings
from tradebot.exchange import create_exchange, market_symbol

log = logging.getLogger("tradebot.check")

EXPECTED_TABLES = {
    "candles", "market_context", "features", "signals", "ai_reviews",
    "positions", "orders", "bot_state", "learnings",
}

SMOKE_PROMPT = """Eres el analista de riesgo de un bot de trading que opera en papel.
Esto es una prueba de conexión: no hay señal real. Responde SOLO con este JSON, sin texto adicional:
{"decision": "veto", "confidence": 1.0, "size_multiplier": 0.0,
 "reasons": ["prueba de conexión"], "risk_flags": []}"""


def check_claude(settings: Settings) -> str:
    analyst = create_analyst(settings.ai)
    review = analyst.review(SMOKE_PROMPT, model=settings.ai.filter_model)
    return (
        f"modelo {review.model}, decisión {review.decision.decision}, "
        f"{review.input_tokens}+{review.output_tokens} tokens, {review.duration_ms} ms"
    )


def check_exchange(settings: Settings) -> str:
    bot = settings.bot
    exchange = create_exchange(bot, load_exchange_credentials(bot.exchange))
    symbol = market_symbol(bot.bases[0], bot.quote, bot.market_type)
    ticker = exchange.fetch_ticker(symbol)
    balance = exchange.fetch_balance()
    quote_free = balance.get("free", {}).get(bot.quote, 0)
    return f"{bot.exchange} testnet ({bot.market_type}): {symbol} = {ticker['last']}, {bot.quote} libre = {quote_free}"


def check_database() -> str:
    with psycopg.connect(load_database_url(), connect_timeout=10) as conn:
        rows = conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        ).fetchall()
    missing = EXPECTED_TABLES - {name for (name,) in rows}
    if missing:
        raise RuntimeError(f"faltan tablas: {', '.join(sorted(missing))} (corre sql/001_schema.sql)")
    return f"{len(EXPECTED_TABLES)} tablas encontradas"


def _run_check(name: str, check: Callable[[], str]) -> bool:
    expected_failures = (
        AIResponseError, QuotaExceededError, RuntimeError, ccxt.BaseError, psycopg.Error, OSError,
    )
    try:
        log.info("%-9s OK    %s", name, check())
        return True
    except expected_failures as exc:
        log.error("%-9s FALLA %s", name, exc)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    results = [
        _run_check("claude", lambda: check_claude(settings)),
        _run_check("exchange", lambda: check_exchange(settings)),
        _run_check("supabase", check_database),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
