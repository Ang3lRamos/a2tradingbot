"""Dashboard del bot: en vivo contra comprar y mantener BTC, aporte de la IA y backtest.

Uso: streamlit run dashboard/app.py
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import data  # noqa: E402

from tradebot.ai_eval import bootstrap_interval, selection_r, selection_skill  # noqa: E402
from tradebot.backtest.metrics import summarize  # noqa: E402

st.set_page_config(page_title="Tradebot", page_icon="📈", layout="wide")
cfg = data.settings()
instance = cfg.bot.instance
theme = getattr(getattr(st.context, "theme", None), "type", None) or "light"

METRIC_LABELS = {
    "retorno_neto": ("Retorno neto", "{:+.2%}"), "max_drawdown": ("Máximo drawdown", "{:.2%}"),
    "sharpe": ("Sharpe", "{:.2f}"), "sortino": ("Sortino", "{:.2f}"), "operaciones": ("Operaciones", "{:,.0f}"),
    "tasa_acierto": ("Tasa de acierto", "{:.1%}"), "ganancia_promedio": ("Ganancia promedio", "{:,.2f}"),
    "perdida_promedio": ("Pérdida promedio", "{:,.2f}"), "profit_factor": ("Profit factor", "{:.2f}"),
    "r_promedio": ("R promedio", "{:+.2f}"), "comisiones": ("Comisiones (USDT)", "{:,.2f}"),
    "funding": ("Funding (USDT)", "{:,.2f}"),
}


def metrics_table(columns: dict[str, dict]) -> pd.DataFrame:
    rows = {}
    for key, (label, fmt) in METRIC_LABELS.items():
        rows[label] = {name: (fmt.format(m[key]) if m.get(key) is not None and np.isfinite(m[key]) else "—")
                       for name, m in columns.items()}
    return pd.DataFrame(rows).T


def equity_section(curves: pd.DataFrame, key: str) -> None:
    st.altair_chart(charts.equity_chart(curves, theme), width="stretch")
    with st.expander("Ver tabla"):
        st.dataframe(curves.rename(columns=charts.SERIES).round(2), width="stretch", key=f"tabla-{key}")


# --- Encabezado: estado del bot ---
st.title("Tradebot")
st.caption(f"Instancia `{instance}` · variante `{cfg.strategy.variant}` · dinero de prueba (Binance Demo)")

state = data.bot_state(instance)
cols = st.columns(4)
if not state:
    st.info("El bot todavía no ha corrido ningún ciclo. Inícialo con `python -m tradebot.run`.")
else:
    heartbeat = state.get("last_heartbeat")
    minutes = (datetime.now(UTC) - heartbeat).total_seconds() / 60 if heartbeat else None
    alive = minutes is not None and minutes < 75
    cols[0].metric("Bot", "✅ Activo" if alive else "⛔ Sin señal de vida",
                   f"último ciclo hace {minutes:.0f} min" if minutes is not None else "sin ciclos", delta_color="off")
    if state.get("kill_switch"):
        cols[1].metric("Modo", "🛑 Kill switch", "requiere revisión manual", delta_color="off")
    elif state.get("mode") == "solo_cierre":
        cols[1].metric("Modo", "⚠️ Solo cierre", state.get("mode_reason") or "", delta_color="off")
    else:
        cols[1].metric("Modo", "✅ Operando", delta_color="off")
    today = state.get("ai_calls_date") == datetime.now(UTC).date()
    cols[2].metric("Llamadas a Claude hoy", f"{state.get('ai_calls_today', 0) if today else 0} / {cfg.ai.daily_call_limit}")
    cols[3].metric("Riesgo por operación", f"{cfg.risk.risk_per_trade:.1%}",
                   f"kill switch al {cfg.risk.max_drawdown:.0%}", delta_color="off")

live_tab, ai_tab, backtest_tab = st.tabs(["En vivo", "Analista IA", "Backtest"])

# --- En vivo ---
with live_tab:
    curves = data.equity_vs_btc(instance)
    all_positions = data.positions(instance)
    closed = all_positions[all_positions["status"] == "closed"]
    if curves.empty:
        st.info("Todavía no hay historial de capital: se registra uno por ciclo.")
    else:
        bot = summarize(curves["equity"], data.live_trades(closed))
        btc = summarize(curves["btc"], pd.DataFrame())
        days = (curves.index[-1] - curves.index[0]).total_seconds() / 86400
        c = st.columns(4)
        c[0].metric("Retorno del bot", f"{bot['retorno_neto']:+.2%}",
                    f"{bot['retorno_neto'] - btc['retorno_neto']:+.2%} vs BTC")
        c[1].metric("Comprar y mantener BTC", f"{btc['retorno_neto']:+.2%}")
        c[2].metric("Máximo drawdown del bot", f"{bot['max_drawdown']:.2%}", delta_color="off")
        c[3].metric("Operaciones cerradas", f"{len(closed)}", f"{days:.1f} días en papel", delta_color="off")
        if len(closed) < 30:
            st.caption(f"Con {len(closed)} operaciones todavía no se puede concluir nada: la meta del plan es 100+.")
        equity_section(curves, "vivo")
        st.subheader("Métricas")
        st.dataframe(metrics_table({"Bot": bot, "Comprar y mantener BTC": btc}), width="stretch")

    st.subheader("Posiciones abiertas")
    open_positions = all_positions[all_positions["status"] == "open"]
    if open_positions.empty:
        st.caption("Ninguna.")
    else:
        st.dataframe(open_positions[["symbol", "side", "qty", "entry_price", "stop_price", "size_multiplier", "opened_at"]],
                     width="stretch", hide_index=True)
    st.subheader("Operaciones cerradas")
    if closed.empty:
        st.caption("Ninguna todavía.")
    else:
        st.dataframe(closed[["symbol", "side", "qty", "entry_price", "exit_price", "pnl", "fees", "exit_reason",
                             "opened_at", "closed_at"]], width="stretch", hide_index=True)
    st.subheader("Alertas recientes")
    st.dataframe(data.alerts(instance), width="stretch", hide_index=True)

# --- Analista IA ---
with ai_tab:
    st.markdown("¿Claude mejora las señales de la estrategia base? Se mide si da **más tamaño a las señales que "
                "salen bien**. Reducir el tamaño de todo no cuenta: si la base pierde, perder menos es solo operar menos.")
    reviews = data.ai_eval_reviews()
    if reviews.empty:
        st.info("Todavía no hay revisiones. Corre `python -m tradebot.ai_eval --n 30`.")
    else:
        rows = reviews[["r", "size"]].to_numpy()
        skill = selection_skill(rows)
        low, high = bootstrap_interval(rows, selection_skill)
        verdict = ("✅ Elige mejor que el azar" if low > 0 else "⛔ Elige peor que el azar" if high < 0
                   else "➖ Todavía no se distingue del azar")
        c = st.columns(4)
        c[0].metric("Señales revisadas", f"{len(reviews)}", "muestra histórica de 300", delta_color="off")
        c[1].metric("Habilidad de selección", f"{skill:+.3f} R", f"intervalo 90%: {low:+.2f} a {high:+.2f}", delta_color="off")
        c[2].metric("R por unidad de riesgo", f"{selection_r(rows):+.3f}", f"sin IA: {reviews['r'].mean():+.3f}", delta_color="off")
        c[3].metric("Veredicto", verdict)
        by_decision = reviews.groupby("decision").agg(
            señales=("r", "size"), R_medio=("r", "mean"), acierto=("r", lambda r: (r > 0).mean()),
            tamaño_medio=("size", "mean")).round(3)
        st.dataframe(by_decision, width="stretch")
        st.caption(f"Tokens promedio por revisión: {reviews['input_tokens'].mean():,.0f} de entrada y "
                   f"{reviews['output_tokens'].mean():,.0f} de salida; {reviews['duration_ms'].mean() / 1000:.1f} s.")

    live_reviews = data.ai_reviews(instance)
    st.subheader("Decisiones en vivo")
    if live_reviews.empty:
        st.caption("Claude todavía no ha revisado señales en vivo.")
    else:
        st.dataframe(live_reviews.groupby("decision").agg(señales=("r", "size"), R_medio=("r", "mean")).round(3),
                     width="stretch")

# --- Backtest ---
with backtest_tab:
    labels = {"is": "In-sample (desarrollo)", "oos": "Out-of-sample (evaluación final)"}
    period = st.radio("Periodo", list(labels), format_func=labels.get, horizontal=True)
    strategy_metrics, btc_metrics, curves = data.backtest(period)
    st.dataframe(metrics_table({cfg.strategy.variant: strategy_metrics, "Comprar y mantener BTC": btc_metrics}),
                 width="stretch")
    equity_section(curves, f"backtest-{period}")
    st.caption("Método y conclusiones: docs/resultados_fase2.md. El periodo out-of-sample se usó una sola vez.")
