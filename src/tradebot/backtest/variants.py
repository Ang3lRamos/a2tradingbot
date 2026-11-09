"""Variantes de estrategia que se comparan en el backtest.

La lista es fija y se definió antes de ver resultados: agregar variantes hasta que una salga
bien es sobreajuste. Si se agrega una, se documenta por qué y se compara contra todas.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

import pandas as pd

from tradebot.backtest.data import MarketData, common_index, period_index, resample_candles, to_arrays
from tradebot.backtest.engine import BacktestResult, run_backtest
from tradebot.backtest.metrics import buy_and_hold
from tradebot.config import Settings, StrategySettings
from tradebot.features.indicators import compute_features
from tradebot.strategy import apply_regime, daily_regime, donchian_signals, generate_signals

SignalFn = Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame]
# Todas las variantes arrancan en la misma fecha: 60 días de calentamiento para EMAs y tendencia diaria.
WARMUP = pd.Timedelta(days=60)


@dataclass(frozen=True)
class Variant:
    name: str
    timeframe: str
    signals: SignalFn
    regime_filter: bool
    take_profit_r: float  # 0 = sin take profit
    trailing_stop: bool
    description: str


def build_variants(strategy: StrategySettings) -> dict[str, Variant]:
    def pullback(candles, features):
        return generate_signals(features, strategy)

    def donchian(lookback):
        return lambda candles, features: donchian_signals(candles, features, lookback)

    variants = [
        Variant("pullback-1h", "1h", pullback, False, 2.0, False, "la estrategia original"),
        Variant("pullback-4h+tend", "4h", pullback, True, 2.0, False, "original en 4h, a favor de la tendencia diaria"),
        Variant("donchian-1h-48", "1h", donchian(48), False, 0, True, "ruptura de 2 días en velas de 1h"),
        Variant("donchian-4h-20", "4h", donchian(20), False, 0, True, "ruptura de ~3 días en velas de 4h"),
        Variant("donchian-4h-55", "4h", donchian(55), False, 0, True, "ruptura de ~9 días en velas de 4h"),
        Variant("donchian-4h-20+tend", "4h", donchian(20), True, 0, True, "ruptura de ~3 días, a favor de la tendencia diaria"),
        Variant("donchian-4h-55+tend", "4h", donchian(55), True, 0, True, "ruptura de ~9 días, a favor de la tendencia diaria"),
    ]
    return {v.name: v for v in variants}


@dataclass(frozen=True)
class VariantRun:
    result: BacktestResult
    benchmark: pd.Series
    index: pd.DatetimeIndex


@dataclass(frozen=True)
class PreparedSymbol:
    candles: pd.DataFrame
    features: pd.DataFrame
    signals: pd.DataFrame
    funding: pd.Series


def prepare_variant(variant: Variant, market: dict[str, MarketData], settings: Settings) -> dict[str, PreparedSymbol]:
    prepared = {}
    for symbol, data in market.items():
        candles = resample_candles(data.candles, variant.timeframe)
        features = compute_features(candles, settings.strategy)
        signals = variant.signals(candles, features)
        if variant.regime_filter:
            signals = apply_regime(signals, daily_regime(candles))
        prepared[symbol] = PreparedSymbol(candles, features, signals, data.funding)
    return prepared


def variant_risk(variant: Variant, settings: Settings, kill_switch: bool = True):
    risk = replace(settings.risk, take_profit_r=variant.take_profit_r)
    return risk if kill_switch else replace(risk, max_drawdown=1.0)


def run_variant(variant: Variant, market: dict[str, MarketData], settings: Settings, period: str,
                kill_switch: bool = True) -> VariantRun:
    prepared = {s: (p.candles, p.features["atr"], p.signals, p.funding)
                for s, p in prepare_variant(variant, market, settings).items()}

    all_candles = [candles for candles, *_ in prepared.values()]
    start = min(c.index[0] for c in all_candles) + WARMUP
    if settings.backtest.is_start:
        start = max(start, pd.Timestamp(settings.backtest.is_start))
    oos_start = pd.Timestamp(settings.backtest.oos_start, tz="UTC")
    index = period_index(common_index(all_candles), start, oos_start, period)

    arrays = {s: to_arrays(c, atr, sig, f, index, variant.timeframe) for s, (c, atr, sig, f) in prepared.items()}
    risk = variant_risk(variant, settings, kill_switch)
    result = run_backtest(index, arrays, risk, settings.backtest, trailing_stop=variant.trailing_stop)

    btc_close = next(iter(prepared.values()))[0]["close"].reindex(index)
    return VariantRun(result, buy_and_hold(btc_close, settings.backtest), index)
