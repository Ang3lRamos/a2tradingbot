"""Tendencia siempre invertida con tamaño por volatilidad (ver docs/investigacion.md, pre-registro).

Cada día, con el cierre: señal = promedio de signo(retorno a 20, 60 y 120 días); peso = señal
× (vol. objetivo / vol. realizada) / n monedas; exposición total topada en 1 (sin apalancamiento).
La posición se mantiene hasta el cierre siguiente. Costos sobre lo operado y funding real.

Uso:
    python -m tradebot.backtest.trend
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradebot.backtest.data import MarketData, load_market
from tradebot.backtest.metrics import max_drawdown
from tradebot.backtest.walkforward import START, annual, daily_sharpe, equal_risk
from tradebot.config import BacktestSettings, load_settings

log = logging.getLogger(__name__)

LOOKBACKS = (20, 60, 120)
VOL_WINDOW = 30
TARGET_VOL = 0.40
REBALANCE_BAND = 0.05
DAYS_PER_YEAR = 365
YEARS = range(2021, 2027)
EVAL_FROM = pd.Timestamp("2022-01-01", tz="UTC")  # mismo tramo que el walk-forward de las rupturas


@dataclass(frozen=True)
class TrendResult:
    equity: pd.Series
    weights: pd.DataFrame
    turnover: float  # suma de |cambio de peso|, promedio anual


def daily_closes(market: dict[str, MarketData]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cierres diarios (solo días completos) y funding diario sumado, por moneda."""
    closes, funding = {}, {}
    for symbol, data in market.items():
        hourly = data.candles["close"]
        days = hourly.resample("1D").agg(["last", "count"])
        closes[symbol] = days.loc[days["count"] == 24, "last"]
        funding[symbol] = data.funding.resample("1D").sum()
    closes = pd.DataFrame(closes)
    return closes, pd.DataFrame(funding).reindex(closes.index).fillna(0.0)


def target_weights(closes: pd.DataFrame, long_only: bool) -> pd.DataFrame:
    signal = sum(np.sign(closes / closes.shift(n) - 1) for n in LOOKBACKS) / len(LOOKBACKS)
    if long_only:
        signal = signal.clip(lower=0)
    vol = closes.pct_change().rolling(VOL_WINDOW).std() * np.sqrt(DAYS_PER_YEAR)
    weights = (signal * (TARGET_VOL / vol) / closes.shape[1]).fillna(0.0)
    gross = weights.abs().sum(axis=1)
    return weights.div(gross.clip(lower=1.0), axis=0)  # si la suma pasa de 1, se reduce todo en proporción


def simulate(closes: pd.DataFrame, funding: pd.DataFrame, targets: pd.DataFrame, costs: BacktestSettings,
             start: pd.Timestamp) -> TrendResult:
    returns = closes.pct_change().fillna(0.0)
    held = np.zeros(closes.shape[1])
    equity, value, history, traded = [], 1.0, [], 0.0
    dates = closes.index[closes.index >= start]
    for today in dates:
        # 1. Resultado del día con la posición que venía del cierre anterior.
        r, f = returns.loc[today].to_numpy(), funding.loc[today].to_numpy()
        value *= 1 + float(held @ r) - float(held @ f)
        # La exposición se desplaza con el precio: lo que subió pesa más.
        held = held * (1 + r) / (1 + float(held @ r)) if value > 0 else held
        # 2. Rebalanceo al cierre, solo en las monedas que se alejaron más de la banda.
        target = targets.loc[today].to_numpy()
        change = np.where(np.abs(target - held) > REBALANCE_BAND, target - held, 0.0)
        value *= 1 - np.abs(change).sum() * (costs.fee_rate + costs.slippage)
        traded += np.abs(change).sum()
        held = held + change
        equity.append(value)
        history.append(held.copy())
    years = (dates[-1] - dates[0]) / pd.Timedelta(days=365.25)
    return TrendResult(pd.Series(equity, index=dates) * costs.initial_capital,
                       pd.DataFrame(history, index=dates, columns=closes.columns), traded / years)


def report(market: dict[str, MarketData], costs: BacktestSettings) -> None:
    closes, funding = daily_closes(market)
    btc = closes.iloc[:, 0][closes.index >= START]
    btc = btc / btc.iloc[0] * costs.initial_capital
    results = {label: simulate(closes, funding, target_weights(closes, long_only), costs, START)
               for label, long_only in (("solo largo", True), ("largo/corto", False))}

    log.info("Tendencia con tamaño por volatilidad (pre-registro en docs/investigacion.md)\n")
    log.info("%-24s" + "%9d" * len(YEARS), "retorno por año", *YEARS)
    for label, res in [*results.items(), ("BTC comprar y mantener", None)]:
        eq = res.equity if res else btc
        cells = [eq[eq.index.year == y] for y in YEARS]
        log.info("%-24s" + " %+7.1f%%" * len(YEARS), label,
                 *[(c.iloc[-1] / c.iloc[0] - 1) * 100 if len(c) > 1 else float("nan") for c in cells])

    log.info("\n2022-2026 %21s %10s %10s %10s %14s", "retorno", "anual", "caída máx", "Sharpe", "exposición")
    btc_eval = btc[btc.index >= EVAL_FROM - pd.Timedelta(days=1)]
    for label, res in results.items():
        eq = res.equity[res.equity.index >= EVAL_FROM - pd.Timedelta(days=1)]
        w = res.weights[res.weights.index >= EVAL_FROM]
        log.info("%-24s %+9.1f%% %+9.1f%% %9.1f%% %10.2f %13.0f%%", label, (eq.iloc[-1] / eq.iloc[0] - 1) * 100,
                 annual(eq) * 100, max_drawdown(eq) * 100, daily_sharpe(eq), w.abs().sum(axis=1).mean() * 100)
        scale, scaled = equal_risk(eq, btc_eval)
        log.info("  %-22s %+9.1f%% %+9.1f%% %9.1f%% %10.2f", f"a igual riesgo (x{scale:.1f})",
                 (scaled.iloc[-1] - 1) * 100, annual(scaled) * 100, max_drawdown(scaled) * 100, daily_sharpe(scaled))
        positive = sum(1 for y in YEARS if len(c := res.equity[res.equity.index.year == y]) > 1 and c.iloc[-1] > c.iloc[0])
        log.info("  años positivos 2021-2026: %d de %d | rotación %.1fx al año", positive, len(YEARS), res.turnover)
    log.info("%-24s %+9.1f%% %+9.1f%% %9.1f%% %10.2f %13s", "BTC comprar y mantener",
             (btc_eval.iloc[-1] / btc_eval.iloc[0] - 1) * 100, annual(btc_eval) * 100, max_drawdown(btc_eval) * 100,
             daily_sharpe(btc_eval), "100%")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    report(load_market(settings), settings.backtest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
