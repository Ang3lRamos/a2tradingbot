"""Backtest de la variante configurada contra comprar y mantener BTC.

Uso:
    python -m tradebot.backtest                     # periodo in-sample (antes de oos_start): para desarrollar
    python -m tradebot.backtest --variante pullback-1h
    python -m tradebot.backtest --sin-kill-switch   # diagnóstico: la estrategia en todo el periodo
    python -m tradebot.backtest --period oos        # evaluación final out-of-sample: correr una sola vez al final

Para comparar todas las variantes: python -m tradebot.backtest.compare
Guarda operaciones y curva de capital en reports/.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from tradebot.backtest.data import load_market
from tradebot.backtest.metrics import summarize
from tradebot.backtest.variants import build_variants, run_variant
from tradebot.config import load_settings

log = logging.getLogger("tradebot.backtest")
REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"


def format_table(rows: dict[str, dict[str, float]]) -> str:
    percent = {"retorno_neto", "max_drawdown", "tasa_acierto"}
    keys = list(dict.fromkeys(k for metrics in rows.values() for k in metrics))
    lines = [f"{'':22}" + "".join(f"{name:>24}" for name in rows)]
    for key in keys:
        cells = []
        for metrics in rows.values():
            value = metrics.get(key)
            if value is None:
                cells.append(f"{'-':>24}")
            elif key in percent:
                cells.append(f"{value:>24.2%}")
            elif key == "operaciones":
                cells.append(f"{value:>24,.0f}")
            else:
                cells.append(f"{value:>24,.2f}")
        lines.append(f"{key:22}" + "".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    variants = build_variants(settings.strategy)
    parser = argparse.ArgumentParser(description="Backtest de una variante de estrategia")
    parser.add_argument("--period", choices=["is", "oos", "all"], default="is")
    parser.add_argument("--variante", choices=list(variants), default=settings.strategy.variant)
    parser.add_argument("--sin-kill-switch", action="store_true",
                        help="diagnóstico: no detener el bot por drawdown, para medir la estrategia en todo el periodo")
    args = parser.parse_args(argv)
    if args.period != "is":
        log.warning("Periodo %s: incluye datos out-of-sample. Úsalo solo para la evaluación final.\n", args.period)

    variant = variants[args.variante]
    run = run_variant(variant, load_market(settings), settings, args.period, kill_switch=not args.sin_kill_switch)
    result = run.result

    log.info("Variante %s (%s)", variant.name, variant.description)
    log.info("Periodo %s: %s a %s (%d velas de %s)\n", args.period, run.index[0], run.index[-1], len(run.index), variant.timeframe)
    log.info(format_table({
        variant.name: summarize(result.equity, result.trades),
        "comprar y mantener BTC": summarize(run.benchmark, pd.DataFrame()),
    }))
    if not result.trades.empty:
        by_symbol = result.trades.groupby(["symbol", "side"])["net_pnl"].agg(["count", "sum"]).round(2)
        log.info("\nPor moneda y dirección (operaciones, P&L neto):\n%s", by_symbol.to_string())
    for event in result.events[:10]:
        log.info("evento: %s", event)
    if len(result.events) > 10:
        log.info("... y %d eventos más", len(result.events) - 10)

    REPORTS_DIR.mkdir(exist_ok=True)
    stem = f"backtest_{variant.name}_{args.period}"
    result.trades.to_csv(REPORTS_DIR / f"{stem}_trades.csv", index=False)
    pd.concat([result.equity, run.benchmark], axis=1).to_csv(REPORTS_DIR / f"{stem}_equity.csv")
    log.info("\nOperaciones y curva de capital en %s", REPORTS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
