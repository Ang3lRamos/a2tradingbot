"""Acceso a Supabase (Postgres). Todas las escrituras son upserts: repetir una carga no duplica nada."""

from datetime import datetime

import psycopg
from psycopg import sql

from tradebot.config import load_database_url
from tradebot.data.candles import Candle
from tradebot.data.context import Point
from tradebot.data.paginate import to_datetime

CONTEXT_COLUMNS = {"funding_rate", "open_interest", "fear_greed"}


def connect() -> psycopg.Connection:
    return psycopg.connect(load_database_url(), connect_timeout=10)


def last_candle_ts(conn: psycopg.Connection, symbol: str, timeframe: str) -> datetime | None:
    row = conn.execute(
        "select max(ts) from candles where symbol = %s and timeframe = %s", (symbol, timeframe)
    ).fetchone()
    return row[0]


def save_candles(conn: psycopg.Connection, symbol: str, timeframe: str, candles: list[Candle]) -> int:
    rows = [(symbol, timeframe, to_datetime(int(c[0])), c[1], c[2], c[3], c[4], c[5]) for c in candles]
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into candles (symbol, timeframe, ts, open, high, low, close, volume)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (symbol, timeframe, ts) do update set
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume = excluded.volume
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _context_column(column: str) -> sql.Identifier:
    if column not in CONTEXT_COLUMNS:
        raise ValueError(f"columna de contexto desconocida: {column}")
    return sql.Identifier(column)


def last_context_ts(conn: psycopg.Connection, symbol: str, column: str) -> datetime | None:
    query = sql.SQL("select max(ts) from market_context where symbol = %s and {} is not null").format(
        _context_column(column)
    )
    return conn.execute(query, (symbol,)).fetchone()[0]


def save_context(conn: psycopg.Connection, symbol: str, column: str, points: list[Point]) -> int:
    """Escribe solo `column`; las demás columnas de la fila quedan como estaban."""
    query = sql.SQL(
        "insert into market_context (symbol, ts, {col}) values (%s, %s, %s) "
        "on conflict (symbol, ts) do update set {col} = excluded.{col}"
    ).format(col=_context_column(column))
    with conn.cursor() as cur:
        cur.executemany(query, [(symbol, to_datetime(ts), value) for ts, value in points])
    conn.commit()
    return len(points)


def candle_gaps(conn: psycopg.Connection, symbol: str, timeframe: str, step_seconds: int) -> list[tuple]:
    """Huecos en la serie: pares (vela anterior, vela siguiente) separados por más de un paso."""
    return conn.execute(
        """
        select prev_ts, ts from (
            select ts, lag(ts) over (order by ts) as prev_ts
            from candles where symbol = %s and timeframe = %s
        ) t
        where ts - prev_ts > make_interval(secs => %s)
        order by ts
        """,
        (symbol, timeframe, step_seconds),
    ).fetchall()
