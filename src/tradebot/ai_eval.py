"""Fase 3: ¿Claude mejora las señales de la estrategia base?

Toma una muestra fija de señales históricas (repartida en todo el periodo), le pide a Claude
que revise cada una con el mismo contexto que tendrá en vivo, y compara el resultado de las
aprobadas contra las vetadas. Cada revisión se guarda en Supabase (signals + ai_reviews).

Uso:
    python -m tradebot.ai_eval --n 10      # revisa hasta 10 señales pendientes (respeta el tope diario)
    python -m tradebot.ai_eval --reporte   # compara resultados de lo revisado hasta ahora

Se puede correr en tandas durante varios días: retoma donde quedó.
"""

import argparse
import logging
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradebot import db
from tradebot.ai import create_analyst
from tradebot.ai.context import AssetFrames, build_context
from tradebot.ai.prompt import PROMPT_VERSION, render_prompt
from tradebot.ai.review import review_signal
from tradebot.backtest.data import load_market
from tradebot.backtest.outcomes import signal_outcome
from tradebot.backtest.variants import WARMUP, build_variants, prepare_variant, variant_risk
from tradebot.config import Settings, load_settings
from tradebot.strategy import LONG, daily_regime

log = logging.getLogger("tradebot.ai_eval")
SAMPLE_SEED = 7
# Fecha de corte fija: si la muestra creciera con datos nuevos, cambiaría qué señales se eligen.
SAMPLE_END = pd.Timestamp("2026-11-09", tz="UTC")


@dataclass(frozen=True)
class SampledSignal:
    symbol: str
    ts: pd.Timestamp
    direction: int
    score: float
    reason: str


def eval_instance(settings: Settings) -> str:
    return f"{settings.bot.instance}-eval-{PROMPT_VERSION}"


def sample_signals(signals: list[SampledSignal], size: int) -> list[SampledSignal]:
    """Muestra repartida en el tiempo y en orden aleatorio fijo: una tanda parcial ya es representativa."""
    ordered = sorted(signals, key=lambda s: (s.ts, s.symbol))
    if len(ordered) > size:
        picks = np.linspace(0, len(ordered) - 1, size).round().astype(int)
        ordered = [ordered[i] for i in sorted(set(picks))]
    rng = np.random.default_rng(SAMPLE_SEED)
    return [ordered[i] for i in rng.permutation(len(ordered))]


def fresh_signals(signals: pd.DataFrame, step: pd.Timedelta) -> pd.DataFrame:
    """Solo la primera vela de cada ruptura: si la vela anterior ya tenía señal en la misma
    dirección, la posición ya estaría abierta y en vivo esa señal no llegaría a la IA."""
    previous = signals["direction"].reindex(signals.index - step).to_numpy()
    return signals[previous != signals["direction"].to_numpy()]


def load_universe(settings: Settings):
    variant = build_variants(settings.strategy)[settings.strategy.variant]
    market = load_market(settings)
    prepared = prepare_variant(variant, market, settings)
    with db.connect() as conn:
        fear_greed = {s: db.load_context(conn, s, "fear_greed") for s in prepared}
    assets = {
        symbol: AssetFrames(p.candles, p.features, daily_regime(p.candles), p.funding, fear_greed[symbol])
        for symbol, p in prepared.items()
    }
    start = min(p.candles.index[0] for p in prepared.values()) + WARMUP
    signals = [
        SampledSignal(symbol, ts, int(row.direction), float(row.score), row.reason)
        for symbol, p in prepared.items()
        for ts, row in fresh_signals(p.signals, pd.Timedelta(variant.timeframe)).iterrows()
        if start <= ts < SAMPLE_END
    ]
    return variant, prepared, assets, signals


def run_reviews(settings: Settings, n: int, sample_size: int) -> int:
    variant, _, assets, signals = load_universe(settings)
    sample = sample_signals(signals, sample_size)
    market_asset = assets[next(iter(assets))]  # el primer símbolo de la config es el referente (BTC)
    step = pd.Timedelta(variant.timeframe)
    analyst = create_analyst(settings.ai)
    instance = eval_instance(settings)
    done = 0

    with db.connect() as conn:
        for signal in sample:
            if done >= n:
                break
            signal_id = db.save_signal(conn, instance, variant.name, signal.symbol, variant.timeframe, signal.ts,
                                       "long" if signal.direction == LONG else "short", signal.score, signal.reason)
            if db.has_ai_review(conn, signal_id):
                continue
            context = build_context(assets[signal.symbol], market_asset, signal.ts, signal.ts + step,
                                    signal.direction, signal.reason, signal.score)
            outcome = review_signal(conn, analyst, settings.ai, settings.bot.instance, signal_id, render_prompt(context))
            if outcome.quota_exhausted:
                log.warning("Cuota agotada: %s. Sigue otro día con el mismo comando.", outcome.error)
                break
            done += 1
            log.info("%3d/%d  señal %d  %s  %-5s -> %s%s", done, n, signal_id, signal.symbol,
                     "long" if signal.direction == LONG else "short", outcome.decision,
                     f" (error: {outcome.error[:80]})" if outcome.error else "")

        reviewed = len(db.load_reviews(conn, instance).query("decision.notna()"))
    log.info("\nRevisadas con éxito: %d de %d en la muestra (%d señales en total).", reviewed, len(sample), len(signals))
    return 0


def selection_r(rows: np.ndarray) -> float:
    """R medio por unidad de riesgo cuando cada señal se opera con el tamaño que asignó la IA."""
    r, size = rows[:, 0], rows[:, 1]
    return float((r * size).sum() / size.sum()) if size.sum() > 0 else float("nan")


def selection_skill(rows: np.ndarray) -> float:
    """Cuánto mejora el R por unidad de riesgo frente a reducir todas las señales por igual.

    Reducir el tamaño de todo no es habilidad: si la base pierde, perder menos es solo operar menos.
    Esta medida es cero si el tamaño no tiene relación con el resultado.
    """
    return selection_r(rows) - float(rows[:, 0].mean())


def bootstrap_interval(values: np.ndarray, statistic, n: int = 5000, level: float = 0.9) -> tuple[float, float]:
    rng = np.random.default_rng(0)
    draws = [statistic(values[rng.integers(0, len(values), len(values))]) for _ in range(n)]
    draws = [d for d in draws if not np.isnan(d)]
    tail = (1 - level) / 2 * 100
    return float(np.percentile(draws, tail)), float(np.percentile(draws, 100 - tail))


def report(settings: Settings) -> int:
    variant, prepared, _, _ = load_universe(settings)
    with db.connect() as conn:
        reviews = db.load_reviews(conn, eval_instance(settings))
    reviews = reviews[reviews["decision"].notna()].copy()
    if reviews.empty:
        log.info("Todavía no hay revisiones. Corre: python -m tradebot.ai_eval --n 10")
        return 0

    risk = variant_risk(variant, settings)
    outcomes = []
    for row in reviews.itertuples():
        p = prepared[row.symbol]
        ts = pd.Timestamp(row.ts)
        outcomes.append(signal_outcome(p.candles, p.features["atr"], p.funding, p.signals.loc[[ts]],
                                       risk, settings.backtest, variant.timeframe, variant.trailing_stop))
    reviews["r"] = outcomes
    reviews["size"] = [
        1.0 if d == "approve" else (min(max(r["size_multiplier"], 0.1), 0.9) if d == "reduce" else 0.0)
        for d, r in zip(reviews["decision"], reviews["response"])
    ]
    reviews = reviews.dropna(subset=["r"])
    oos_start = pd.Timestamp(settings.backtest.oos_start, tz="UTC")

    log.info("Revisiones: %d (modelo %s, prompt %s)\n", len(reviews), reviews["model"].iloc[0], PROMPT_VERSION)
    log.info("%-10s %6s %10s %12s %10s", "decisión", "n", "R medio", "acierto", "R total")
    for decision, group in reviews.groupby("decision"):
        log.info("%-10s %6d %10.2f %11.1f%% %10.1f", decision, len(group), group["r"].mean(),
                 (group["r"] > 0).mean() * 100, group["r"].sum())
    log.info("%-10s %6d %10.2f %11.1f%% %10.1f", "todas", len(reviews), reviews["r"].mean(),
             (reviews["r"] > 0).mean() * 100, reviews["r"].sum())

    log.info("\nTamaño medio asignado por la IA: %.2f", reviews["size"].mean())
    log.info("R por unidad de riesgo  sin IA: %+.3f | con IA: %+.3f",
             reviews["r"].mean(), selection_r(reviews[["r", "size"]].to_numpy()))
    skill = selection_skill(reviews[["r", "size"]].to_numpy())
    low, high = bootstrap_interval(reviews[["r", "size"]].to_numpy(), selection_skill)
    log.info("Habilidad de selección: %+.3f R por unidad de riesgo (intervalo 90%%: %+.3f a %+.3f)", skill, low, high)
    log.info("  (compara contra reducir todas las señales por igual al mismo tamaño medio)")
    if low > 0:
        log.info("-> La IA elige mejor que el azar con evidencia estadística en esta muestra.")
    elif high < 0:
        log.info("-> La IA elige peor que el azar con evidencia estadística en esta muestra.")
    else:
        log.info("-> Todavía no se distingue la habilidad de la IA del azar: hacen falta más revisiones.")

    for label, part in (("in-sample", reviews[reviews["ts"] < oos_start]), ("out-of-sample", reviews[reviews["ts"] >= oos_start])):
        if len(part):
            log.info("  %-14s n=%3d  sin IA %+.3f R  con IA %+.3f R por unidad de riesgo", label, len(part),
                     part["r"].mean(), selection_r(part[["r", "size"]].to_numpy()))
    log.info("\nTokens promedio: %.0f entrada, %.0f salida | duración promedio %.1f s",
             reviews["input_tokens"].mean(), reviews["output_tokens"].mean(), reviews["duration_ms"].mean() / 1000)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Evaluación del analista IA sobre señales históricas")
    parser.add_argument("--n", type=int, default=10, help="señales a revisar en esta tanda")
    parser.add_argument("--muestra", type=int, default=300, help="tamaño total de la muestra fija")
    parser.add_argument("--reporte", action="store_true", help="solo mostrar resultados")
    args = parser.parse_args(argv)
    settings = load_settings()
    return report(settings) if args.reporte else run_reviews(settings, args.n, args.muestra)


if __name__ == "__main__":
    sys.exit(main())
