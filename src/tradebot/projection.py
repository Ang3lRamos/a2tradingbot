"""Ruta proyectada vs ruta real: qué rango de capital era esperable según el backtest.

Bootstrap por bloques de los retornos diarios del backtest: se arman muchos caminos posibles pegando
tramos de 20 días seguidos (para conservar rachas y volatilidad agrupada) y se toman los percentiles 10, 50
y 90 de cada día. Si la curva real se sale de la banda por mucho tiempo, el bot no se comporta como lo probado.

Es una referencia a agresividad 1 (la del backtest), no una promesa: asume que el futuro se parece al pasado.
"""

import numpy as np
import pandas as pd

from tradebot.backtest.trend import EVAL_FROM, daily_closes, simulate, target_weights
from tradebot.backtest.variants import build_variants, run_variant
from tradebot.backtest.walkforward import START
from tradebot.config import Settings

PATHS = 2000
BLOCK_DAYS = 20
MIN_HORIZON_DAYS = 90
EXTRA_DAYS = 30        # la banda sigue un mes más allá de hoy
PERCENTILES = (10, 50, 90)


def daily_returns(equity: pd.Series) -> np.ndarray:
    daily = equity.resample("1D").last().dropna()
    return daily.pct_change().dropna().to_numpy()


def bands(returns: np.ndarray, start_equity: float, days: int, paths: int = PATHS, block: int = BLOCK_DAYS,
          seed: int = 7) -> pd.DataFrame:
    """Percentiles del capital para los días 0..days. Fila 0 = capital inicial."""
    if len(returns) < block:
        raise ValueError("historia del backtest demasiado corta para la proyección")
    rng = np.random.default_rng(seed)
    n_blocks = -(-days // block)
    starts = rng.integers(0, len(returns) - block + 1, size=(paths, n_blocks))
    sampled = returns[starts[..., None] + np.arange(block)].reshape(paths, -1)[:, :days]
    equity = start_equity * np.cumprod(1 + sampled, axis=1)
    equity = np.hstack([np.full((paths, 1), start_equity), equity])
    return pd.DataFrame({f"p{q}": np.percentile(equity, q, axis=0) for q in PERCENTILES})


def projection(returns: np.ndarray, start: pd.Timestamp, start_equity: float, now: pd.Timestamp, source: str) -> dict:
    days = max(MIN_HORIZON_DAYS, int((now - start) / pd.Timedelta(days=1)) + EXTRA_DAYS)
    table = bands(returns, start_equity, days)
    dates = pd.date_range(start, periods=days + 1, freq="1D")
    return {
        "inicio": start.isoformat(), "capital_inicial": start_equity, "fuente": source,
        "puntos": [{"t": d.isoformat(), **{k: float(v) for k, v in row.items()}} for d, (_, row) in zip(dates, table.iterrows())],
    }


def breakout_returns(settings: Settings, market) -> np.ndarray:
    """Backtest in-sample de la variante activa (con el que se eligió; el OOS se reserva)."""
    variant = build_variants(settings.strategy)[settings.strategy.variant]
    return daily_returns(run_variant(variant, market, settings, "is").result.equity)


def trend_returns(settings: Settings, market) -> np.ndarray:
    """Backtest 2022-2026 de la tendencia, el mismo tramo de la evaluación documentada."""
    closes, funding = daily_closes(market)
    equity = simulate(closes, funding, target_weights(closes, settings.trend.long_only), settings.backtest, START).equity
    return daily_returns(equity[equity.index >= EVAL_FROM])
