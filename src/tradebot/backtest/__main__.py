"""Backtest de la estrategia base contra comprar y mantener BTC.

Uso:
    python -m tradebot.backtest              # periodo in-sample (antes de oos_start): para desarrollar
    python -m tradebot.backtest --period oos # evaluación final out-of-sample: correr una sola vez al final
    python -m tradebot.backtest --sin-kill-switch  # diagnóstico: la estrategia en todo el periodo

Guarda operaciones y curva de capital en reports/.
"""

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from tradebot import db
from tradebot.backtest.engine import SymbolData, run_backtest
from tradebot.backtest.metrics import buy_and_hold, summarize
from tradebot.config import Settings, load_settings
from tradebot.exchange import market_symbol
from tradebot.features.indicators import compute_features
from tradebot.strategy import generate_signals

log = logging.getLogger("tradebot.backtest")
REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"


def load_symbol(conn, symbol: str, settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    candles = db.load_candles(conn, symbol, settings.bot.timeframe)
    features = compute_features(candles, settings.strategy)
    funding = db.load_context(conn, symbol, "funding_rate")
    # Binance a veces marca el funding unos milisegundos después de la hora en punto.
    funding.index = pd.DatetimeIndex(funding.index).floor("h")
    return candles.join(features[["atr"]]), generate_signals(features, settings.strategy), funding


def to_arrays(frame: pd.DataFrame, signals: pd.DataFrame, funding: pd.Series, index: pd.DatetimeIndex) -> SymbolData:
    frame = frame.reindex(index)
    signals = signals.reindex(index)
    return SymbolData(
        open=frame["open"].to_numpy(), high=frame["high"].to_numpy(), low=frame["low"].to_numpy(),
        close=frame["close"].to_numpy(), atr=frame["atr"].to_numpy(),
        signal=signals["direction"].fillna(0).to_numpy(), score=signals["score"].fillna(0).to_numpy(),
        funding=funding.groupby(level=0).sum().reindex(index).fillna(0).to_numpy(),
    )


def period_index(frames: list[pd.DataFrame], warmup: int, oos_start: pd.Timestamp, period: str) -> pd.DatetimeIndex:
    index = frames[0].index
    for frame in frames[1:]:
        index = index.intersection(frame.index)
    index = index[warmup:]
    if period == "is":
        return index[index < oos_start]
    if period == "oos":
        return index[index >= oos_start]
    return index


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
    parser = argparse.ArgumentParser(description="Backtest de la estrategia base")
    parser.add_argument("--period", choices=["is", "oos", "all"], default="is")
    parser.add_argument("--sin-kill-switch", action="store_true",
                        help="diagnóstico: no detener el bot por drawdown, para medir la estrategia en todo el periodo")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.sin_kill_switch:
        settings = replace(settings, risk=replace(settings.risk, max_drawdown=1.0))
    oos_start = pd.Timestamp(settings.backtest.oos_start, tz="UTC")
    if args.period != "is":
        log.warning("Periodo %s: incluye datos out-of-sample. Úsalo solo para la evaluación final.\n", args.period)

    symbols = [market_symbol(base, settings.bot.quote, settings.bot.market_type) for base in settings.bot.bases]
    with db.connect() as conn:
        loaded = {symbol: load_symbol(conn, symbol, settings) for symbol in symbols}

    warmup = settings.strategy.ema_slow * 3
    index = period_index([frame for frame, _, _ in loaded.values()], warmup, oos_start, args.period)
    data = {symbol: to_arrays(frame, signals, funding, index) for symbol, (frame, signals, funding) in loaded.items()}
    result = run_backtest(index, data, settings.risk, settings.backtest)

    btc_close = loaded[symbols[0]][0]["close"].reindex(index)
    benchmark = buy_and_hold(btc_close, settings.backtest)
    log.info("Periodo %s: %s a %s (%d velas de %s)\n", args.period, index[0], index[-1], len(index), settings.bot.timeframe)
    log.info(format_table({
        "estrategia base": summarize(result.equity, result.trades),
        "comprar y mantener BTC": summarize(benchmark, pd.DataFrame()),
    }))
    if not result.trades.empty:
        by_symbol = result.trades.groupby("symbol")["net_pnl"].agg(["count", "sum"]).round(2)
        log.info("\nPor moneda (operaciones, P&L neto):\n%s", by_symbol.to_string())
    for event in result.events[:10]:
        log.info("evento: %s", event)
    if len(result.events) > 10:
        log.info("... y %d eventos más", len(result.events) - 10)

    REPORTS_DIR.mkdir(exist_ok=True)
    result.trades.to_csv(REPORTS_DIR / f"backtest_{args.period}_trades.csv", index=False)
    pd.concat([result.equity, benchmark], axis=1).to_csv(REPORTS_DIR / f"backtest_{args.period}_equity.csv")
    log.info("\nOperaciones y curva de capital en %s", REPORTS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
