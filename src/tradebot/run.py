"""Bot en vivo (cuenta demo). Cada hora: ingesta de datos y un ciclo de trading.

Uso:
    python -m tradebot.run            # corre indefinidamente, a los 2 minutos de cada hora (UTC)
    python -m tradebot.run --once     # un solo ciclo y termina
    python -m tradebot.run --reanudar # quita el kill switch o el modo solo cierre después de revisar a mano

Además, a las 00:15 UTC corre el bot de tendencia en su cuenta virtual (tradebot.live.trend_paper),
y el día 1 de cada mes manda su resumen mensual por Telegram (tradebot.live.trend_report).
"""

import argparse
import logging
import sys

import psycopg
from apscheduler.schedulers.blocking import BlockingScheduler

from tradebot import db, ingest
from tradebot.ai import create_analyst
from tradebot.ai_eval import load_universe
from tradebot.broker.ccxt_broker import CCXTBroker
from tradebot.config import Settings, load_exchange_credentials, load_settings
from tradebot.exchange import create_exchange
from tradebot.live.cycle import Cycle, Snapshot
from tradebot.live.store import LiveStore
from tradebot.live.trend_paper import mark_to_market
from tradebot.live.trend_paper import run_and_notify as run_trend
from tradebot.live.trend_report import send_monthly
from tradebot.notify import create_notifier, failure_card
from tradebot.publish import publish

log = logging.getLogger("tradebot.run")


def load_snapshot(settings: Settings) -> Snapshot:
    variant, prepared, assets, _ = load_universe(settings)
    return Snapshot(variant.name, variant.timeframe, assets, {s: p.signals for s, p in prepared.items()})


def run_once(settings: Settings) -> int:
    notifier = create_notifier(source=settings.bot.instance)
    try:
        events = _cycle(settings, notifier)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo del ciclo se avisa; el scheduler sigue
        log.exception("el ciclo falló")
        notifier.send("critical", f"el ciclo falló: {type(exc).__name__}: {str(exc)[:300]}", failure_card("el ciclo", exc))
        try:
            with db.connect() as conn:
                LiveStore(conn, settings.bot.instance).alert("critical", f"el ciclo falló: {exc}")
        except psycopg.Error:
            log.exception("tampoco se pudo guardar la alerta (¿base caída?)")
        return 1
    log.info("ciclo terminado: %d eventos", len(events))
    try:
        mark_to_market(settings)
    except Exception:  # noqa: BLE001 - la cuenta virtual no debe tumbar el ciclo real
        log.exception("no se pudo valorar la cuenta de tendencia")
    try:
        # Datos para el dashboard web. Si falla, el bot sigue: solo el dashboard queda desactualizado.
        log.info("dashboard: publicado %s", ", ".join(publish(settings)))
    except Exception:  # noqa: BLE001 - nada del dashboard debe tumbar el ciclo
        log.exception("no se pudieron publicar los datos del dashboard")
    return 0


def _cycle(settings: Settings, notifier) -> list[str]:
    if ingest.main([]) != 0:
        log.warning("la ingesta tuvo fallas; el ciclo sigue con los datos disponibles")
    with db.connect() as conn:
        store = LiveStore(conn, settings.bot.instance)
        broker = CCXTBroker(create_exchange(settings.bot, load_exchange_credentials(settings.bot.exchange)),
                            settings.bot.quote)
        return Cycle(settings, store, broker, create_analyst(settings.ai), notifier).run(load_snapshot(settings))


def run_trend_and_publish(settings: Settings) -> int:
    status = run_trend(settings)
    try:
        publish(settings)
    except Exception:  # noqa: BLE001 - el dashboard es secundario
        log.exception("no se pudieron publicar los datos del dashboard")
    return status


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
    # Después de la ingesta de las 00:02, que trae la última vela de 1h del día.
    scheduler.add_job(run_trend_and_publish, "cron", hour=0, minute=15, args=[settings], max_instances=1, coalesce=True)
    # El día 1, después del cierre diario de las 00:15: resumen del mes anterior.
    scheduler.add_job(send_monthly, "cron", day=1, hour=0, minute=40, args=[settings], max_instances=1, coalesce=True)
    log.info("bot en marcha: un ciclo a los 2 minutos de cada hora, tendencia a las 00:15 y resumen mensual "
             "el día 1 a las 00:40 (UTC). Ctrl+C para detener.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("bot detenido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
