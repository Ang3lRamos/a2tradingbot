"""Walk-forward: elegir la variante con los datos pasados y medirla en el año siguiente.

Para cada año de prueba se elige, entre las variantes fijas, la de mejor Sharpe en todo lo anterior
(ventana creciente). El resultado encadena esos años: es lo que habría obtenido alguien que eligiera
así cada enero, sin ver el futuro. Corre sin kill switch para medir la ventaja de la estrategia;
el kill switch es una protección aparte.

Uso:
    python -m tradebot.backtest.walkforward
"""

import logging
from dataclasses import dataclass

import pandas as pd

from tradebot.backtest.data import MarketData, common_index, load_market, to_arrays
from tradebot.backtest.engine import run_backtest
from tradebot.backtest.metrics import buy_and_hold, max_drawdown, sharpe
from tradebot.backtest.variants import PreparedSymbol, Variant, build_variants, prepare_variant, variant_risk
from tradebot.config import Settings, load_settings

log = logging.getLogger(__name__)

# Primera fecha con las 3 monedas (SOL desde 2020-09-14) más 60 días de calentamiento.
START = pd.Timestamp("2020-11-14", tz="UTC")
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]


@dataclass(frozen=True)
class Window:
    equity: pd.Series   # diaria, al cierre de cada día
    btc: pd.Series      # BTC comprar y mantener, diaria
    trades: int


def run_window(variant: Variant, prepared: dict[str, PreparedSymbol], settings: Settings,
               start: pd.Timestamp, end: pd.Timestamp) -> Window:
    """Backtest de la variante entre `start` y `end` con capital nuevo. Indicadores calculados con toda la historia."""
    index = common_index([p.candles for p in prepared.values()])
    index = index[(index >= start) & (index < end)]
    arrays = {s: to_arrays(p.candles, p.features["atr"], p.signals, p.funding, index, variant.timeframe)
              for s, p in prepared.items()}
    risk = variant_risk(variant, settings, kill_switch=False)
    result = run_backtest(index, arrays, risk, settings.backtest, trailing_stop=variant.trailing_stop)
    btc_close = next(iter(prepared.values())).candles["close"].reindex(index)
    btc = buy_and_hold(btc_close, settings.backtest)
    return Window(result.equity.resample("1D").last().dropna(), btc.resample("1D").last().dropna(), len(result.trades))


def daily_sharpe(equity: pd.Series) -> float:
    return sharpe(equity.pct_change().dropna())


def chain(pieces: list[pd.Series]) -> pd.Series:
    """Une curvas de capital de tramos consecutivos en una sola, compuesta."""
    returns = pd.concat([p.pct_change().fillna(0.0) for p in pieces])
    return (1 + returns).cumprod()


def equal_risk(bot: pd.Series, btc: pd.Series) -> tuple[float, pd.Series]:
    """Escala los retornos diarios del bot hasta igualar la volatilidad de BTC (implica apalancamiento)."""
    bot_r, btc_r = bot.pct_change().dropna(), btc.pct_change().dropna()
    scale = float(btc_r.std() / bot_r.std())
    return scale, (1 + bot_r * scale).cumprod()


def annual(equity: pd.Series) -> float:
    years = (equity.index[-1] - equity.index[0]) / pd.Timedelta(days=365.25)
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def run(settings: Settings, market: dict[str, MarketData]) -> None:
    variants = build_variants(settings.strategy)
    prepared = {name: prepare_variant(v, market, settings) for name, v in variants.items()}
    now = min(p.candles.index[-1] for p in next(iter(prepared.values())).values()) + pd.Timedelta(hours=1)
    years = [(y, pd.Timestamp(f"{y}-01-01", tz="UTC"), min(pd.Timestamp(f"{y + 1}-01-01", tz="UTC"), now))
             for y in range(START.year + 1, TEST_YEARS[-1] + 1)]

    # 1. Cada variante, año por año (capital nuevo cada año).
    log.info("Retorno por año, sin kill switch (riesgo %.1f%% por operación)\n", settings.risk.risk_per_trade * 100)
    log.info("%-22s" + "%9s" * len(years), "variante", *[str(y) for y, *_ in years])
    btc_by_year = {}
    for name, v in variants.items():
        cells = []
        for y, start, end in years:
            w = run_window(v, prepared[name], settings, start, end)
            cells.append(f"{w.equity.iloc[-1] / w.equity.iloc[0] - 1:+8.1%}")
            btc_by_year[y] = w.btc.iloc[-1] / w.btc.iloc[0] - 1
        log.info("%-22s" + " %s" * len(cells), name, *cells)
    log.info("%-22s" + " %+8.1f%%" * len(years), "BTC comprar y mantener", *[btc_by_year[y] * 100 for y, *_ in years])

    # 2. Walk-forward: cada año se opera la variante con mejor Sharpe en todo lo anterior.
    log.info("\nWalk-forward (elige con los datos previos, opera el año siguiente)\n")
    log.info("%-6s %-22s %14s %10s %10s %6s", "año", "elegida", "Sharpe previo", "retorno", "BTC", "ops")
    bot_pieces, btc_pieces = [], []
    for y, start, end in years:
        if y not in TEST_YEARS:
            continue
        train = {name: daily_sharpe(run_window(v, prepared[name], settings, START, start).equity)
                 for name, v in variants.items()}
        chosen = max(train, key=train.get)
        w = run_window(variants[chosen], prepared[chosen], settings, start, end)
        bot_pieces.append(w.equity)
        btc_pieces.append(w.btc)
        log.info("%-6d %-22s %14.2f %+9.1f%% %+9.1f%% %6d", y, chosen, train[chosen],
                 (w.equity.iloc[-1] / w.equity.iloc[0] - 1) * 100, (w.btc.iloc[-1] / w.btc.iloc[0] - 1) * 100, w.trades)

    # 3. Resumen y comparación a igual riesgo.
    bot, btc = chain(bot_pieces), chain(btc_pieces)
    scale, scaled = equal_risk(bot, btc)
    log.info("\n%-30s %10s %10s %10s %10s", "", "retorno", "anual", "caída máx", "Sharpe")
    for label, eq in (("bot (walk-forward)", bot), (f"bot a igual riesgo (x{scale:.1f})", scaled), ("BTC comprar y mantener", btc)):
        log.info("%-30s %+9.1f%% %+9.1f%% %9.1f%% %10.2f", label, (eq.iloc[-1] / eq.iloc[0] - 1) * 100,
                 annual(eq) * 100, max_drawdown(eq) * 100, daily_sharpe(eq))
    log.info("\n'A igual riesgo' escala el bot hasta la volatilidad de BTC; requeriría ~x%.1f de apalancamiento.", scale)
    log.info("Variantes evaluadas: %d (la selección en cada año es entre todas ellas).", len(variants))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    run(settings, load_market(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
