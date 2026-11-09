"""Publica los datos del dashboard en Supabase (tabla dashboard_snapshots).

El dashboard web (Vercel) no llega a este PC: lee estos JSON con un usuario de solo lectura.

Uso:
    python -m tradebot.publish                 # resumen; IA y backtest si tienen más de un día
    python -m tradebot.publish --todo          # recalcula todo
    python -m tradebot.publish --crear-lector  # define la contraseña del usuario de solo lectura
"""

import argparse
import logging
import secrets
import sys
from datetime import timedelta
from pathlib import Path

from psycopg import sql
from psycopg.types.json import Jsonb

from tradebot import db, reporting
from tradebot.config import Settings, load_settings

log = logging.getLogger("tradebot.publish")
SLOW_REFRESH = timedelta(hours=24)
PROJECT_REF = "qvzketramsyskygyqjac"
ROOT = Path(__file__).resolve().parents[2]
READER_SQL = ROOT / "sql" / "005_dashboard_reader.sql"


def _save(key: str, data: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "insert into dashboard_snapshots (key, data, updated_at) values (%s, %s, now()) "
            "on conflict (key) do update set data = excluded.data, updated_at = now()", (key, Jsonb(data)))
        conn.commit()


def _age(key: str) -> timedelta | None:
    with db.connect() as conn:
        row = conn.execute("select now() - updated_at from dashboard_snapshots where key = %s", (key,)).fetchone()
    return row[0] if row else None


def publish(settings: Settings, everything: bool = False) -> list[str]:
    jobs = {
        "resumen": lambda: reporting.clean({"estado": reporting.bot_state(settings),
                                            "mercados": reporting.markets(settings),
                                            "vivo": reporting.live(settings)}),
        "ia": lambda: reporting.ai(settings),
        "backtest_is": lambda: reporting.backtest(settings, "is"),
        "backtest_oos": lambda: reporting.backtest(settings, "oos"),
    }
    published = []
    for key, compute in jobs.items():
        age = _age(key)
        if key != "resumen" and not everything and age is not None and age < SLOW_REFRESH:
            continue
        _save(key, compute())
        published.append(key)
    return published


def create_reader() -> str:
    """Crea (si falta) el usuario de solo lectura, le pone una contraseña nueva y devuelve su URL (para Vercel)."""
    password = secrets.token_urlsafe(24)
    with db.connect() as conn:
        conn.execute(READER_SQL.read_text(encoding="utf-8"))
        conn.execute(sql.SQL("alter role dashboard_reader with password {}").format(sql.Literal(password)))
        conn.commit()
    host = db.load_database_url().rsplit("@", 1)[1]
    return f"postgresql://dashboard_reader.{PROJECT_REF}:{password}@{host}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Publica los datos del dashboard")
    parser.add_argument("--todo", action="store_true")
    parser.add_argument("--crear-lector", action="store_true")
    args = parser.parse_args(argv)
    if args.crear_lector:
        from dotenv import set_key
        url = create_reader()
        for env_file in (ROOT / ".env", ROOT / "web" / ".env.local"):
            env_file.touch(exist_ok=True)
            set_key(str(env_file), "DASHBOARD_DATABASE_URL", url, quote_mode="never")
        log.info("Usuario dashboard_reader listo. Su URL quedó en .env y web/.env.local (DASHBOARD_DATABASE_URL);")
        log.info("cópiala a Vercel: Settings > Environment Variables.")
        return 0
    log.info("publicado: %s", ", ".join(publish(load_settings(), args.todo)) or "nada (todo al día)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
