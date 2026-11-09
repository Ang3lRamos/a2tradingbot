"""Compara todas las variantes en el periodo in-sample, dividido en sub-periodos.

Uso: python -m tradebot.backtest.compare

El kill switch se desactiva para medir cada estrategia en todo el periodo; el máximo drawdown
dice si en vivo lo habría activado. Se elige la variante que se mantiene positiva en la mayoría
de los sub-periodos, no la de mejor retorno total.
"""

import argparse
import logging
import sys

import pandas as pd

from tradebot.backtest.data import load_market
from tradebot.backtest.metrics import summarize
from tradebot.backtest.variants import build_variants, run_variant
from tradebot.config import load_settings

log = logging.getLogger("tradebot.compare")


def subperiod_returns(equity: pd.Series, n: int) -> list[float]:
    chunks = [chunk for chunk in pd.Series(range(len(equity))).groupby(
        pd.cut(range(len(equity)), n, labels=False)).groups.values()]
    returns, previous_end = [], equity.iloc[0]
    for positions in chunks:
        end = equity.iloc[positions[-1]]
        returns.append(end / previous_end - 1)
        previous_end = end
    return returns


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Compara variantes de estrategia (in-sample)")
    parser.add_argument("--subperiodos", type=int, default=4)
    args = parser.parse_args(argv)
    settings = load_settings()
    market = load_market(settings)
    n = args.subperiodos

    rows, benchmark_row, bounds = [], None, None
    for variant in build_variants(settings.strategy).values():
        run = run_variant(variant, market, settings, period="is", kill_switch=False)
        metrics = summarize(run.result.equity, run.result.trades)
        parts = subperiod_returns(run.result.equity, n)
        rows.append((variant.name, metrics, parts))
        if benchmark_row is None:
            bench_parts = subperiod_returns(run.benchmark, n)
            benchmark_row = ("comprar y mantener BTC", summarize(run.benchmark, pd.DataFrame()), bench_parts)
            edges = pd.cut(range(len(run.index)), n, labels=False)
            bounds = [run.index[edges == k][0].strftime("%Y-%m") for k in range(n)]
            log.info("Periodo in-sample: %s a %s, kill switch desactivado\n", run.index[0].date(), run.index[-1].date())

    header = f"{'variante':24}{'retorno':>9}{'max DD':>9}{'sharpe':>8}{'ops':>6}{'PF':>6}{'costos':>8}  " + \
             "".join(f"{b:>9}" for b in bounds) + "  positivos"
    log.info(header)
    log.info("-" * len(header))
    for name, m, parts in rows + [benchmark_row]:
        costs = m.get("comisiones", 0) + m.get("funding", 0)
        pf = m.get("profit_factor")
        log.info(
            f"{name:24}{m['retorno_neto']:>9.1%}{m['max_drawdown']:>9.1%}{m['sharpe']:>8.2f}"
            f"{m['operaciones']:>6}{(f'{pf:.2f}' if pf is not None else '-'):>6}{costs:>8.0f}  "
            + "".join(f"{p:>9.1%}" for p in parts) + f"  {sum(p > 0 for p in parts)}/{n}"
        )
    log.info("\nSub-periodos: retorno de cada tramo de igual duración. Costos = comisiones + funding (USDT).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
