"""Acceso a Supabase (Postgres). Todas las escrituras son upserts: repetir una carga no duplica nada."""

from datetime import datetime

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

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


def load_candles(conn: psycopg.Connection, symbol: str, timeframe: str) -> pd.DataFrame:
    rows = conn.execute(
        "select ts, open, high, low, close, volume from candles "
        "where symbol = %s and timeframe = %s order by ts",
        (symbol, timeframe),
    ).fetchall()
    frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    return frame.astype(float)


def load_context(conn: psycopg.Connection, symbol: str, column: str) -> pd.Series:
    query = sql.SQL("select ts, {col} from market_context where symbol = %s and {col} is not null order by ts").format(
        col=_context_column(column)
    )
    rows = conn.execute(query, (symbol,)).fetchall()
    return pd.Series({ts: float(value) for ts, value in rows}, name=column, dtype=float)


def last_features_ts(conn: psycopg.Connection, symbol: str, timeframe: str) -> datetime | None:
    row = conn.execute(
        "select max(ts) from features where symbol = %s and timeframe = %s", (symbol, timeframe)
    ).fetchone()
    return row[0]


def save_features(conn: psycopg.Connection, symbol: str, timeframe: str, features: pd.DataFrame) -> int:
    """Una fila por vela; los indicadores aún sin datos suficientes (NaN) se omiten del JSON."""
    rows = [
        (symbol, timeframe, ts, Jsonb({k: round(float(v), 8) for k, v in values.items() if pd.notna(v)}))
        for ts, values in features.iterrows()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "insert into features (symbol, timeframe, ts, indicators) values (%s, %s, %s, %s) "
            "on conflict (symbol, timeframe, ts) do update set indicators = excluded.indicators",
            rows,
        )
    conn.commit()
    return len(rows)


def save_signal(conn: psycopg.Connection, instance: str, strategy: str, symbol: str, timeframe: str,
                ts: datetime, direction: str, score: float, reason: str) -> int:
    """Registra una señal (idempotente) y devuelve su id."""
    row = conn.execute(
        """
        insert into signals (instance, strategy, symbol, timeframe, ts, direction, score, reason)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (instance, strategy, symbol, timeframe, ts) do update set score = excluded.score
        returning id
        """,
        (instance, strategy, symbol, timeframe, ts, direction, score, reason),
    ).fetchone()
    conn.commit()
    return row[0]


def has_ai_review(conn: psycopg.Connection, signal_id: int) -> bool:
    """Solo cuenta revisiones con decisión: las que fallaron se pueden reintentar."""
    row = conn.execute("select 1 from ai_reviews where signal_id = %s and decision is not null", (signal_id,))
    return row.fetchone() is not None


def save_ai_review(conn: psycopg.Connection, signal_id: int, model: str, prompt: str, response: dict | None,
                   decision: str | None, error: str | None, input_tokens: int | None,
                   output_tokens: int | None, duration_ms: int | None) -> None:
    conn.execute(
        """
        insert into ai_reviews (signal_id, model, prompt, response, decision, error,
                                input_tokens, output_tokens, duration_ms)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (signal_id) do update set
            model = excluded.model, prompt = excluded.prompt, response = excluded.response,
            decision = excluded.decision, error = excluded.error, input_tokens = excluded.input_tokens,
            output_tokens = excluded.output_tokens, duration_ms = excluded.duration_ms, created_at = now()
        """,
        (signal_id, model, prompt, Jsonb(response) if response is not None else None, decision, error,
         input_tokens, output_tokens, duration_ms),
    )
    conn.commit()


def reserve_ai_call(conn: psycopg.Connection, instance: str, daily_limit: int) -> bool:
    """Suma una llamada al contador del día si queda cupo. Atómico: dos procesos no pueden pasarse del tope."""
    conn.execute("insert into bot_state (instance) values (%s) on conflict do nothing", (instance,))
    row = conn.execute(
        """
        update bot_state set
            ai_calls_today = case when ai_calls_date = current_date then ai_calls_today + 1 else 1 end,
            ai_calls_date = current_date
        where instance = %s and (ai_calls_date is distinct from current_date or ai_calls_today < %s)
        returning ai_calls_today
        """,
        (instance, daily_limit),
    ).fetchone()
    conn.commit()
    return row is not None


def load_reviews(conn: psycopg.Connection, instance: str) -> pd.DataFrame:
    rows = conn.execute(
        """
        select s.id, s.symbol, s.ts, s.direction, s.score, r.decision, r.response, r.error, r.model,
               r.input_tokens, r.output_tokens, r.duration_ms
        from signals s join ai_reviews r on r.signal_id = s.id
        where s.instance = %s order by s.ts
        """,
        (instance,),
    ).fetchall()
    columns = ["signal_id", "symbol", "ts", "direction", "score", "decision", "response", "error", "model",
               "input_tokens", "output_tokens", "duration_ms"]
    return pd.DataFrame(rows, columns=columns)
