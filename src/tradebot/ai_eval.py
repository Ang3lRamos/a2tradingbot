"""Fase 3: ¿Claude mejora las señales de la estrategia base?

Toma una muestra fija de señales históricas (repartida en todo el periodo), le pide a Claude
que revise cada una con el mismo contexto que tendrá en vivo, y compara el resultado de las
aprobadas contra las vetadas. Cada revisión se guarda en Supabase (signals + ai_reviews).

Uso:
    python -m tradebot.ai_eval --n 10      # revisa hasta 10 señales pendientes (respeta el tope diario)
    python -m tradebot.ai_eval --reporte   # compara resultados de lo revisado hasta ahora
    python -m tradebot.ai_eval --prompt v2 --modelo opus --n 30   # experimento v2 (docs/investigacion.md)

Se puede correr en tandas durante varios días: retoma donde quedó.
"""

import argparse
import logging
import sys
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from tradebot import db
from tradebot.ai import create_analyst
from tradebot.ai.context import AssetFrames, build_context, build_context_v2
from tradebot.ai.prompt import render_prompt
from tradebot.ai.review import review_signal, size_for
from tradebot.backtest.data import load_market
from tradebot.backtest.outcomes import signal_outcome
from tradebot.backtest.variants import WARMUP, build_variants, prepare_variant, variant_risk
from tradebot.config import Settings, load_settings
from tradebot.strategy import LONG, daily_regime

log = logging.getLogger("tradebot.ai_eval")
SAMPLE_SEED = 7
SAMPLE_SIZE = 300

# Fecha de corte fija: si la muestra creciera con datos nuevos, cambiaría qué señales se eligen.
SAMPLE_START = pd.Timestamp("2024-01-09 06:00", tz="UTC")
SAMPLE_END = pd.Timestamp("2026-11-09", tz="UTC")


@dataclass(frozen=True)
class SampledSignal:
    symbol: str
    ts: pd.Timestamp
    direction: int
    score: float
    reason: str


@dataclass(frozen=True)
class EvalSpec:
    seed: int
    context: object          # build_context o build_context_v2
    excludes: str | None     # versión cuya muestra no se puede repetir


# Cada versión del prompt se evalúa sobre su propia muestra fija (ver docs/investigacion.md).
EVALS = {
    "v1": EvalSpec(seed=SAMPLE_SEED, context=build_context, excludes=None),
    "v2": EvalSpec(seed=11, context=build_context_v2, excludes="v1"),
}


def eval_instance(settings: Settings, version: str = "v1") -> str:
    return f"{settings.bot.instance}-eval-{version}"


def sample_for(version: str, signals: list[SampledSignal], size: int) -> list[SampledSignal]:
    spec = EVALS[version]
    if spec.excludes:
        used = {(s.symbol, s.ts) for s in sample_for(spec.excludes, signals, size)}
        signals = [s for s in signals if (s.symbol, s.ts) not in used]
    return sample_signals(signals, size, spec.seed)


def sample_signals(signals: list[SampledSignal], size: int, seed: int = SAMPLE_SEED) -> list[SampledSignal]:
    """Muestra repartida en el tiempo y en orden aleatorio fijo: una tanda parcial ya es representativa."""
    ordered = sorted(signals, key=lambda s: (s.ts, s.symbol))
    if len(ordered) > size:
        picks = np.linspace(0, len(ordered) - 1, size).round().astype(int)
        ordered = [ordered[i] for i in sorted(set(picks))]
    rng = np.random.default_rng(seed)
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
    start = max(min(p.candles.index[0] for p in prepared.values()) + WARMUP, SAMPLE_START)
    signals = [
        SampledSignal(symbol, ts, int(row.direction), float(row.score), row.reason)
        for symbol, p in prepared.items()
        for ts, row in fresh_signals(p.signals, pd.Timedelta(variant.timeframe)).iterrows()
        if start <= ts < SAMPLE_END
    ]
    return variant, prepared, assets, signals


def run_reviews(settings: Settings, n: int, sample_size: int, version: str = "v1", model: str | None = None) -> int:
    variant, _, assets, signals = load_universe(settings)
    sample = sample_for(version, signals, sample_size)
    spec = EVALS[version]
    market_asset = assets[next(iter(assets))]  # el primer símbolo de la config es el referente (BTC)
    step = pd.Timedelta(variant.timeframe)
    analyst = create_analyst(settings.ai)
    eval_ai = replace(settings.ai, daily_call_limit=settings.ai.eval_daily_call_limit,
                      decision_model=model or settings.ai.decision_model)
    instance = eval_instance(settings, version)
    done = 0

    with db.connect() as conn:
        # Una sola tanda a la vez: dos procesos revisarían las mismas señales y las contarían dos veces.
        # El candado es de la sesión: se suelta solo al cerrar la conexión, aunque el proceso se caiga.
        if not conn.execute("select pg_try_advisory_lock(hashtext(%s))", (instance,)).fetchone()[0]:
            log.warning("Ya hay una evaluación %s corriendo en otra terminal. Espera a que termine.", version)
            return 1
        for signal in sample:
            if done >= n:
                break
            signal_id = db.save_signal(conn, instance, variant.name, signal.symbol, variant.timeframe, signal.ts,
                                       "long" if signal.direction == LONG else "short", signal.score, signal.reason)
            if db.has_ai_review(conn, signal_id):
                continue
            context = spec.context(assets[signal.symbol], market_asset, signal.ts, signal.ts + step,
                                   signal.direction, signal.reason, signal.score)
            outcome = review_signal(conn, analyst, eval_ai, instance, signal_id, render_prompt(context, version=version))
            if outcome.quota_exhausted:
                log.warning("Cuota agotada: %s. Sigue otro día con el mismo comando.", outcome.error)
                break
            done += 1
            log.info("%3d/%d  señal %d  %s  %-5s -> %s%s", done, n, signal_id, signal.symbol,
                     "long" if signal.direction == LONG else "short", outcome.decision,
                     f" (error: {outcome.error[:80]})" if outcome.error else "")

        reviewed = len(db.load_reviews(conn, instance).query("decision.notna()"))
    if done:
        from tradebot.publish import publish_ai  # import local: publish depende de este módulo

        try:
            publish_ai(settings)
            log.info("dashboard: panel de IA actualizado")
        except Exception:  # noqa: BLE001 - la tanda ya quedó guardada; el dashboard es secundario
            log.exception("no se pudo actualizar el panel de IA del dashboard")
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


# Señales de la misma semana tienden a terminar igual (BTC, ETH y SOL se mueven juntos y las
# operaciones duran días): se remuestrean semanas completas para no subestimar el ruido.
BLOCK = "7D"


def bootstrap_interval(values: np.ndarray, statistic, n: int = 5000, level: float = 0.9,
                       blocks: np.ndarray | None = None) -> tuple[float, float]:
    """Intervalo por bootstrap. Con `blocks`, remuestrea grupos completos (block bootstrap) en vez de filas."""
    rng = np.random.default_rng(0)
    if blocks is None:
        groups = [np.array([i]) for i in range(len(values))]
    else:
        groups = [np.flatnonzero(blocks == b) for b in np.unique(blocks)]
    draws = []
    for _ in range(n):
        picked = rng.integers(0, len(groups), len(groups))
        draws.append(statistic(values[np.concatenate([groups[i] for i in picked])]))
    draws = [d for d in draws if not np.isnan(d)]
    tail = (1 - level) / 2 * 100
    return float(np.percentile(draws, tail)), float(np.percentile(draws, 100 - tail))


def skill_interval(reviews: pd.DataFrame, by_week: bool = True) -> tuple[float, float]:
    """Intervalo 90% de la habilidad de selección; por defecto remuestreando semanas completas."""
    blocks = pd.to_datetime(reviews["ts"], utc=True).dt.floor(BLOCK).to_numpy() if by_week else None
    return bootstrap_interval(reviews[["r", "size"]].to_numpy(), selection_skill, blocks=blocks)


def scored_reviews(settings: Settings, instance: str) -> pd.DataFrame:
    """Revisiones con decisión, más el resultado (R) de cada señal y el tamaño que asignó la IA."""
    variant, prepared, _, _ = load_universe(settings)
    with db.connect() as conn:
        reviews = db.load_reviews(conn, instance)
    reviews = reviews[reviews["decision"].notna() & reviews["symbol"].isin(prepared)].copy()
    if reviews.empty:
        return reviews.assign(r=pd.Series(dtype=float), size=pd.Series(dtype=float))

    risk = variant_risk(variant, settings)
    outcomes = []
    for row in reviews.itertuples():
        p = prepared[row.symbol]
        ts = pd.Timestamp(row.ts)
        outcomes.append(signal_outcome(p.candles, p.features["atr"], p.funding, p.signals.loc[[ts]], risk,
                                       settings.backtest, variant.timeframe, variant.trailing_stop)
                        if ts in p.signals.index else np.nan)
    reviews["r"] = outcomes
    # v2: el tamaño es el puntaje/100 tal cual; v1: el tamaño que resulta de la decisión.
    reviews["score"] = [r.get("score") for r in reviews["response"]]
    reviews["size"] = [s / 100 if s is not None else size_for(d, float(r.get("size_multiplier", 0)))
                       for s, d, r in zip(reviews["score"], reviews["decision"], reviews["response"])]
    return reviews.dropna(subset=["r"])


def rank_correlation(rows: np.ndarray) -> float:
    """Spearman entre el puntaje (columna 1) y el R (columna 0)."""
    if len(rows) < 3 or np.std(rows[:, 1]) == 0:
        return float("nan")
    return float(pd.Series(rows[:, 0]).rank().corr(pd.Series(rows[:, 1]).rank()))


def report(settings: Settings, version: str = "v1") -> int:
    reviews = scored_reviews(settings, eval_instance(settings, version))
    if reviews.empty:
        log.info("Todavía no hay revisiones. Corre: python -m tradebot.ai_eval --n 10")
        return 0
    oos_start = pd.Timestamp(settings.backtest.oos_start, tz="UTC")

    log.info("Revisiones: %d (modelo %s, prompt %s)\n", len(reviews), reviews["model"].iloc[0], version)
    if reviews["score"].notna().all():
        rows = reviews[["r", "score"]].to_numpy(dtype=float)
        blocks = pd.to_datetime(reviews["ts"], utc=True).dt.floor(BLOCK).to_numpy()
        rho = rank_correlation(rows)
        low, high = bootstrap_interval(rows, rank_correlation, blocks=blocks)
        log.info("Puntaje: medio %.0f, desvío %.0f, rango %d-%d", reviews["score"].mean(), reviews["score"].std(),
                 reviews["score"].min(), reviews["score"].max())
        log.info("Correlación puntaje-R (Spearman): %+.3f (intervalo 90%%, por semanas: %+.3f a %+.3f)", rho, low, high)
        log.info("-> %s\n", "El puntaje ordena las señales mejor que el azar (criterio pre-registrado cumplido)." if low > 0
                 else "No hay evidencia de que el puntaje ordene las señales mejor que el azar.")
        terciles = pd.qcut(reviews["score"].rank(method="first"), 3, labels=["bajo", "medio", "alto"])
        for label, group in reviews.groupby(terciles, observed=True):
            log.info("  tercil %-5s puntaje %3.0f-%3.0f  n=%3d  R medio %+.3f  acierto %.0f%%", label, group["score"].min(),
                     group["score"].max(), len(group), group["r"].mean(), (group["r"] > 0).mean() * 100)
        log.info("")
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
    low, high = skill_interval(reviews)
    naive_low, naive_high = skill_interval(reviews, by_week=False)
    log.info("Habilidad de selección: %+.3f R por unidad de riesgo (intervalo 90%%: %+.3f a %+.3f)", skill, low, high)
    log.info("  intervalo por semanas completas (%d semanas); señal por señal sería %+.3f a %+.3f",
             pd.to_datetime(reviews["ts"], utc=True).dt.floor(BLOCK).nunique(), naive_low, naive_high)
    log.info("  (compara contra reducir todas las señales por igual al mismo tamaño medio)")
    if low > 0:
        log.info("-> La IA elige mejor que el azar con evidencia estadística en esta muestra.")
    elif high < 0:
        log.info("-> La IA elige peor que el azar con evidencia estadística en esta muestra.")
    else:
        log.info("-> No se distingue la habilidad de la IA del azar en esta muestra%s.",
                 "" if len(reviews) >= SAMPLE_SIZE else ": faltan revisiones para completarla")

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
    parser.add_argument("--muestra", type=int, default=SAMPLE_SIZE, help="tamaño total de la muestra fija")
    parser.add_argument("--reporte", action="store_true", help="solo mostrar resultados")
    parser.add_argument("--prompt", choices=sorted(EVALS), default="v1", help="versión del prompt a evaluar")
    parser.add_argument("--modelo", help="modelo de Claude (por defecto el de settings.toml)")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.reporte:
        return report(settings, args.prompt)
    return run_reviews(settings, args.n, args.muestra, args.prompt, args.modelo)


if __name__ == "__main__":
    sys.exit(main())
