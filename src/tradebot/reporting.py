"""Datos para el dashboard: estado del bot, curva de capital, posiciones, IA y backtest.

Todo devuelve tipos simples (dict, list) listos para serializar a JSON.
"""

import math
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from tradebot import db
from tradebot.ai_eval import bootstrap_interval, eval_instance, scored_reviews, selection_r, selection_skill
from tradebot.backtest.data import load_market
from tradebot.backtest.metrics import buy_and_hold, summarize
from tradebot.backtest.variants import build_variants, run_variant
from tradebot.config import Settings
from tradebot.exchange import market_symbol

MAX_POINTS = 800
_cache: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: float, compute: Callable[[], object]):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = compute()
    _cache[key] = (time.monotonic(), value)
    return value


def clean(value):
    """NaN e infinitos no existen en JSON: se envían como null."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def thin(curves: pd.DataFrame, max_points: int = MAX_POINTS) -> pd.DataFrame:
    if len(curves) <= max_points:
        return curves
    step = -(-len(curves) // max_points)
    return pd.concat([curves.iloc[::step], curves.iloc[[-1]]]).loc[lambda df: ~df.index.duplicated(keep="last")]


def curve_points(curves: pd.DataFrame) -> list[dict]:
    return [{"t": ts.isoformat(), "bot": float(row.equity), "btc": float(row.btc)}
            for ts, row in thin(curves).iterrows()]


def _query(sql: str, params: tuple) -> list[tuple]:
    with db.connect() as conn:
        return conn.execute(sql, params).fetchall()


# --- estado y mercado ---

def bot_state(settings: Settings) -> dict:
    rows = _query("select mode, mode_reason, kill_switch, last_heartbeat, ai_calls_today, ai_calls_date "
                  "from bot_state where instance = %s", (settings.bot.instance,))
    now = datetime.now(UTC)
    base = {"instancia": settings.bot.instance, "variante": settings.strategy.variant,
            "riesgo_por_operacion": settings.risk.risk_per_trade, "kill_switch_pct": settings.risk.max_drawdown,
            "limite_ia_diario": settings.ai.daily_call_limit, "ahora": now}
    if not rows:
        return base | {"modo": None, "activo": False}
    mode, reason, kill, heartbeat, calls, calls_date = rows[0]
    minutes = (now - heartbeat).total_seconds() / 60 if heartbeat else None
    return base | {
        "modo": "kill_switch" if kill else mode, "motivo": reason, "ultimo_ciclo": heartbeat,
        "minutos_desde_ciclo": minutes, "activo": minutes is not None and minutes < 75,
        "llamadas_ia_hoy": calls if calls_date == now.date() else 0,
    }


def markets(settings: Settings) -> list[dict]:
    result = []
    for base in settings.bot.bases:
        symbol = market_symbol(base, settings.bot.quote, settings.bot.market_type)
        rows = _query("select ts, close from candles where symbol = %s and timeframe = %s order by ts desc limit 25",
                      (symbol, settings.bot.timeframe))
        if not rows:
            continue
        closes = [float(r[1]) for r in rows]
        result.append({"simbolo": base, "precio": closes[0], "ts": rows[0][0],
                       "cambio_24h": closes[0] / closes[24] - 1 if len(closes) > 24 else None,
                       "serie_24h": closes[::-1]})
    return result


# --- en vivo ---

def _equity_vs_btc(settings: Settings) -> pd.DataFrame:
    rows = _query("select ts, equity from equity_snapshots where instance = %s order by ts", (settings.bot.instance,))
    if not rows:
        return pd.DataFrame(columns=["equity", "btc"])
    equity = pd.DataFrame(rows, columns=["ts", "equity"]).astype({"equity": float})
    btc_symbol = market_symbol(settings.bot.bases[0], settings.bot.quote, settings.bot.market_type)
    btc = pd.DataFrame(_query("select ts, close from candles where symbol = %s and timeframe = %s and ts >= %s order by ts",
                              (btc_symbol, settings.bot.timeframe, equity["ts"].iloc[0] - pd.Timedelta("2h"))),
                       columns=["ts", "close"]).astype({"close": float})
    merged = pd.merge_asof(equity, btc, on="ts", direction="backward").dropna()
    if merged.empty:
        return pd.DataFrame(columns=["equity", "btc"])
    costs = replace(settings.backtest, initial_capital=float(merged["equity"].iloc[0]))
    merged["btc"] = buy_and_hold(merged["close"].reset_index(drop=True), costs).to_numpy()
    return merged.set_index("ts")[["equity", "btc"]]


def _positions(settings: Settings) -> pd.DataFrame:
    columns = ["id", "simbolo", "lado", "cantidad", "entrada", "stop", "salida", "pnl", "comisiones", "riesgo",
               "tamano_ia", "estado", "motivo_salida", "abierta", "cerrada"]
    rows = _query("select id, symbol, side, qty, entry_price, stop_price, exit_price, pnl, fees, risk_distance, "
                  "size_multiplier, status, exit_reason, opened_at, closed_at from positions where instance = %s "
                  "order by opened_at desc", (settings.bot.instance,))
    df = pd.DataFrame(rows, columns=columns)
    for col in ["cantidad", "entrada", "stop", "salida", "pnl", "comisiones", "riesgo", "tamano_ia"]:
        df[col] = pd.to_numeric(df[col])
    return df


def live(settings: Settings) -> dict:
    curves = _equity_vs_btc(settings)
    positions = _positions(settings)
    closed = positions[positions["estado"] == "closed"]
    trades = pd.DataFrame({
        "net_pnl": closed["pnl"].fillna(0), "fees": closed["comisiones"].fillna(0), "funding": 0.0,
        "r_multiple": (closed["pnl"] / (closed["riesgo"] * closed["cantidad"]).where(lambda r: r > 0)).fillna(0),
    })
    alerts = _query("select created_at, level, message from alerts where instance = %s order by created_at desc limit 100",
                    (settings.bot.instance,))
    has_curve = len(curves) > 1
    return clean({
        "curva": curve_points(curves) if len(curves) else [],
        "metricas_bot": summarize(curves["equity"], trades) if has_curve else None,
        "metricas_btc": summarize(curves["btc"], pd.DataFrame()) if has_curve else None,
        "capital_actual": float(curves["equity"].iloc[-1]) if len(curves) else None,
        "dias_en_papel": (curves.index[-1] - curves.index[0]).total_seconds() / 86400 if len(curves) else 0,
        "posiciones_abiertas": positions[positions["estado"] == "open"].to_dict("records"),
        "operaciones_cerradas": closed.to_dict("records"),
        "alertas": [{"fecha": a[0], "nivel": a[1], "mensaje": a[2]} for a in alerts],
    })


# --- analista IA ---

def _ai_summary(reviews: pd.DataFrame) -> dict | None:
    if reviews.empty:
        return None
    rows = reviews[["r", "size"]].to_numpy()
    low, high = bootstrap_interval(rows, selection_skill)
    by_decision = [
        {"decision": d, "senales": len(g), "r_medio": g["r"].mean(), "acierto": (g["r"] > 0).mean(),
         "tamano_medio": g["size"].mean()}
        for d, g in reviews.groupby("decision")
    ]
    return {
        "revisadas": len(reviews), "habilidad": selection_skill(rows), "intervalo": [low, high],
        "veredicto": "mejor" if low > 0 else "peor" if high < 0 else "indistinguible",
        "r_sin_ia": reviews["r"].mean(), "r_con_ia": selection_r(rows), "tamano_medio": reviews["size"].mean(),
        "por_decision": by_decision,
        "tokens_entrada": reviews["input_tokens"].mean(), "tokens_salida": reviews["output_tokens"].mean(),
        "segundos": reviews["duration_ms"].mean() / 1000,
    }


def ai(settings: Settings) -> dict:
    return clean({
        "evaluacion": _ai_summary(scored_reviews(settings, eval_instance(settings))),
        "muestra": 300,
        "en_vivo": _ai_summary(scored_reviews(settings, settings.bot.instance)),
    })


# --- backtest ---

def backtest(settings: Settings, period: str) -> dict:
    variant = build_variants(settings.strategy)[settings.strategy.variant]
    run = run_variant(variant, load_market(settings), settings, period)
    curves = pd.DataFrame({"equity": run.result.equity, "btc": run.benchmark})
    return clean({
        "periodo": period, "variante": variant.name, "descripcion": variant.description,
        "desde": run.index[0], "hasta": run.index[-1], "kill_switch": run.result.killed_at,
        "metricas_bot": summarize(run.result.equity, run.result.trades),
        "metricas_btc": summarize(run.benchmark, pd.DataFrame()),
        "curva": curve_points(curves),
    })
