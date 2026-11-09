"""Consultas del dashboard, con caché para no golpear Supabase en cada interacción."""

from dataclasses import replace

import pandas as pd
import streamlit as st

from tradebot import db
from tradebot.ai_eval import eval_instance, scored_reviews
from tradebot.backtest.data import load_market
from tradebot.backtest.metrics import buy_and_hold, summarize
from tradebot.backtest.variants import build_variants, run_variant
from tradebot.config import load_settings
from tradebot.exchange import market_symbol

LIVE_TTL = 60
SLOW_TTL = 3600


@st.cache_resource
def settings():
    return load_settings()


def _query(sql: str, params: tuple, columns: list[str]) -> pd.DataFrame:
    with db.connect() as conn:
        return pd.DataFrame(conn.execute(sql, params).fetchall(), columns=columns)


@st.cache_data(ttl=LIVE_TTL)
def bot_state(instance: str) -> dict:
    df = _query("select mode, mode_reason, kill_switch, last_heartbeat, ai_calls_today, ai_calls_date "
                "from bot_state where instance = %s", (instance,),
                ["mode", "mode_reason", "kill_switch", "last_heartbeat", "ai_calls_today", "ai_calls_date"])
    return df.iloc[0].to_dict() if len(df) else {}


@st.cache_data(ttl=LIVE_TTL)
def equity_vs_btc(instance: str) -> pd.DataFrame:
    """Capital del bot y comprar-y-mantener BTC con el mismo capital inicial, por hora."""
    equity = _query("select ts, equity from equity_snapshots where instance = %s order by ts", (instance,),
                    ["ts", "equity"])
    if equity.empty:
        return equity
    equity["equity"] = equity["equity"].astype(float)
    cfg = settings()
    btc_symbol = market_symbol(cfg.bot.bases[0], cfg.bot.quote, cfg.bot.market_type)
    btc = _query("select ts, close from candles where symbol = %s and timeframe = %s and ts >= %s order by ts",
                 (btc_symbol, cfg.bot.timeframe, equity["ts"].iloc[0] - pd.Timedelta("2h")), ["ts", "close"])
    btc["close"] = btc["close"].astype(float)
    merged = pd.merge_asof(equity, btc, on="ts", direction="backward").dropna()
    if merged.empty:
        return merged
    costs = replace(cfg.backtest, initial_capital=float(merged["equity"].iloc[0]))
    merged["btc"] = buy_and_hold(merged["close"].reset_index(drop=True), costs).to_numpy()
    return merged.set_index("ts")[["equity", "btc"]]


@st.cache_data(ttl=LIVE_TTL)
def positions(instance: str) -> pd.DataFrame:
    df = _query(
        "select id, symbol, side, qty, entry_price, stop_price, exit_price, pnl, fees, risk_distance, "
        "size_multiplier, status, exit_reason, opened_at, closed_at from positions where instance = %s "
        "order by opened_at desc", (instance,),
        ["id", "symbol", "side", "qty", "entry_price", "stop_price", "exit_price", "pnl", "fees", "risk_distance",
         "size_multiplier", "status", "exit_reason", "opened_at", "closed_at"])
    for col in ["qty", "entry_price", "stop_price", "exit_price", "pnl", "fees", "risk_distance", "size_multiplier"]:
        df[col] = pd.to_numeric(df[col])
    return df


def live_trades(closed: pd.DataFrame) -> pd.DataFrame:
    """Posiciones cerradas en el formato que espera `summarize`."""
    risk = (closed["risk_distance"] * closed["qty"]).where(lambda r: r > 0)
    return pd.DataFrame({"net_pnl": closed["pnl"].fillna(0), "fees": closed["fees"].fillna(0), "funding": 0.0,
                         "r_multiple": (closed["pnl"] / risk).fillna(0)})


@st.cache_data(ttl=LIVE_TTL)
def alerts(instance: str, limit: int = 50) -> pd.DataFrame:
    return _query("select created_at, level, message from alerts where instance = %s order by created_at desc limit %s",
                  (instance, limit), ["fecha", "nivel", "mensaje"])


@st.cache_data(ttl=SLOW_TTL, show_spinner="Calculando el resultado de cada señal revisada…")
def ai_reviews(instance: str) -> pd.DataFrame:
    return scored_reviews(settings(), instance)


def ai_eval_reviews() -> pd.DataFrame:
    return ai_reviews(eval_instance(settings()))


@st.cache_data(ttl=SLOW_TTL * 24, show_spinner="Corriendo el backtest…")
def backtest(period: str) -> tuple[dict, dict, pd.DataFrame]:
    cfg = settings()
    variant = build_variants(cfg.strategy)[cfg.strategy.variant]
    run = run_variant(variant, load_market(cfg), cfg, period)
    curves = pd.DataFrame({"equity": run.result.equity, "btc": run.benchmark})
    return summarize(run.result.equity, run.result.trades), summarize(run.benchmark, pd.DataFrame()), curves
