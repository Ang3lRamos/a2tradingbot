"""Agresividad de cada bot, ajustable desde el dashboard (ver sql/007_controls.sql).

Es un multiplicador sobre el tamaño que define la estrategia:
- rupturas: multiplica el riesgo por operación (0,3% × agresividad);
- tendencia: multiplica la exposición objetivo, siempre con la suma topada en 1 (sin apalancamiento).
1 = exactamente lo que se probó en el backtest.
"""

from datetime import datetime

import pandas as pd

MIN_AGGRESSIVENESS = 0.25
MAX_AGGRESSIVENESS = 2.0
STEP = 0.25


def valid_aggressiveness(value: float) -> bool:
    steps = (value - MIN_AGGRESSIVENESS) / STEP
    return MIN_AGGRESSIVENESS <= value <= MAX_AGGRESSIVENESS and abs(steps - round(steps)) < 1e-9


def get_aggressiveness(conn, instance: str) -> float:
    row = conn.execute("select aggressiveness from bot_controls where instance = %s", (instance,)).fetchone()
    return float(row[0]) if row else 1.0


def set_aggressiveness(conn, instance: str, value: float) -> None:
    if not valid_aggressiveness(value):
        raise ValueError(f"agresividad fuera de rango: {value}")
    with conn.transaction():
        conn.execute(
            "insert into bot_controls (instance, aggressiveness, updated_at) values (%s, %s, now()) "
            "on conflict (instance) do update set aggressiveness = excluded.aggressiveness, updated_at = now()",
            (instance, value))
        conn.execute("insert into control_changes (instance, aggressiveness) values (%s, %s)", (instance, value))


def aggressiveness_at(changes: list[tuple[datetime, float]], closes: pd.DatetimeIndex) -> pd.Series:
    """Agresividad vigente en cada cierre diario. El cierre del día D es a las 00:00 del D+1:
    vale el último cambio hecho hasta ese instante; sin cambios previos, 1."""
    values = []
    ordered = sorted(changes)
    for day in closes:
        close_ts = day + pd.Timedelta(days=1)
        current = 1.0
        for changed_at, value in ordered:
            if pd.Timestamp(changed_at) > close_ts:
                break
            current = float(value)
        values.append(current)
    return pd.Series(values, index=closes, dtype=float)


def load_changes(conn, instance: str) -> list[tuple[datetime, float]]:
    rows = conn.execute("select changed_at, aggressiveness from control_changes where instance = %s order by changed_at",
                        (instance,)).fetchall()
    return [(r[0], float(r[1])) for r in rows]
