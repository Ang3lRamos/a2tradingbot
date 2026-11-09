"""Bot en vivo (cuenta demo). Cada hora: ingesta de datos y un ciclo de trading.

Uso:
    python -m tradebot.run            # corre indefinidamente, a los 2 minutos de cada hora (UTC)
    python -m tradebot.run --once     # un solo ciclo y termina
    python -m tradebot.run --reanudar # quita el kill switch o el modo solo cierre después de revisar a mano
"""

import argparse
import logging
import sys

import ccxt
import psycopg
from apscheduler.schedulers.blocking import BlockingScheduler

from tradebot import db, ingest
from tradebot.ai import create_analyst
from tradebot.ai_eval import load_universe
from tradebot.broker.base import BrokerError
from tradebot.broker.ccxt_broker import CCXTBroker
from tradebot.config import Settings, load_exchange_credentials, load_settings
from tradebot.exchange import create_exchange
from tradebot.live.cycle import Cycle, Snapshot
from tradebot.live.store import LiveStore

log = logging.getLogger("tradebot.run")


def load_snapshot(settings: Settings) -> Snapshot:
    variant, prepared, assets, _ = load_universe(settings)
    return Snapshot(variant.name, variant.timeframe, assets, {s: p.signals for s, p in prepared.items()})


def run_once(settings: Settings) -> int:
    if ingest.main([]) != 0:
        log.warning("la ingesta tuvo fallas; el ciclo sigue con los datos disponibles")
    with db.connect() as conn:
        store = LiveStore(conn, settings.bot.instance)
        try:
            broker = CCXTBroker(create_exchange(settings.bot, load_exchange_credentials(settings.bot.exchange)),
                                settings.bot.quote)
            events = Cycle(settings, store, broker, create_analyst(settings.ai)).run(load_snapshot(settings))
        except (BrokerError, ccxt.BaseError, psycopg.Error, OSError) as exc:
            conn.rollback()
            store.alert("critical", f"el ciclo falló: {exc}")
            log.exception("el ciclo falló")
            return 1
    log.info("ciclo terminado: %d eventos", len(events))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Bot de trading en la cuenta demo")
    parser.add_argument("--once", action="store_true", help="un solo ciclo")
    parser.add_argument("--reanudar", action="store_true", help="quitar kill switch / solo cierre")
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.reanudar:
        with db.connect() as conn:
            LiveStore(conn, settings.bot.instance).resume()
        log.info("bot reanudado: modo operar, kill switch desactivado, pico de capital reiniciado")
        return 0
    if args.once:
        return run_once(settings)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_once, "cron", minute=2, args=[settings], max_instances=1, coalesce=True)
    log.info("bot en marcha: un ciclo a los 2 minutos de cada hora (UTC). Ctrl+C para detener.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("bot detenido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
