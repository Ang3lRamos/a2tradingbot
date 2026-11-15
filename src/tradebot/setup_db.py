"""Crea o actualiza el esquema de la base: aplica en orden todos los archivos de sql/.

Cada archivo es idempotente, así que se puede correr las veces que haga falta (por ejemplo,
después de un `git pull` que traiga un archivo nuevo). Los usuarios del dashboard quedan creados
sin contraseña; se la ponen `python -m tradebot.publish --crear-lector` y `--crear-operador`.

Uso: python -m tradebot.setup_db
"""

import logging
import sys
from pathlib import Path

from tradebot import db

log = logging.getLogger("tradebot.setup_db")
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scripts = sorted(SQL_DIR.glob("*.sql"))
    with db.connect() as conn:
        for script in scripts:
            conn.execute(script.read_text(encoding="utf-8"))
            conn.commit()
            log.info("OK  %s", script.name)
    log.info("Esquema al día (%d archivos).", len(scripts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
