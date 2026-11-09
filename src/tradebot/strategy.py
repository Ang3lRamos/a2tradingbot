"""Estrategia base, sin IA: seguir la tendencia y entrar cuando termina un retroceso.

Long:  EMA rápida > EMA lenta (tendencia alcista) y el RSI cruza hacia arriba `rsi_long_trigger`.
Short: EMA rápida < EMA lenta (tendencia bajista) y el RSI cruza hacia abajo `rsi_short_trigger`.

La señal se calcula al cierre de la vela t; la entrada ocurre en la apertura de t+1.
Puntaje: separación entre las EMAs medida en ATRs (qué tan clara es la tendencia).
"""

import numpy as np
import pandas as pd

from tradebot.config import StrategySettings
from tradebot.features.indicators import ema

LONG, SHORT, FLAT = 1, -1, 0


def generate_signals(features: pd.DataFrame, settings: StrategySettings) -> pd.DataFrame:
    rsi, prev_rsi = features["rsi"], features["rsi"].shift()
    uptrend = features["ema_fast"] > features["ema_slow"]
    downtrend = features["ema_fast"] < features["ema_slow"]

    long_entry = uptrend & (prev_rsi < settings.rsi_long_trigger) & (rsi >= settings.rsi_long_trigger)
    short_entry = downtrend & (prev_rsi > settings.rsi_short_trigger) & (rsi <= settings.rsi_short_trigger)

    direction = np.select([long_entry, short_entry], [LONG, SHORT], default=FLAT)
    score = ((features["ema_fast"] - features["ema_slow"]).abs() / features["atr"]).round(3)
    reason = np.select(
        [long_entry, short_entry],
        [f"tendencia alcista y RSI cruza arriba {settings.rsi_long_trigger:g}",
         f"tendencia bajista y RSI cruza abajo {settings.rsi_short_trigger:g}"],
        default="",
    )
    signals = pd.DataFrame({"direction": direction, "score": score, "reason": reason}, index=features.index)
    return signals[signals["direction"] != FLAT]


def donchian_signals(candles: pd.DataFrame, features: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Ruptura de canal: long si el cierre supera el máximo de las `lookback` velas anteriores,
    short si cae bajo su mínimo. El canal excluye la vela actual (shift) para no mirar al futuro.
    Puntaje: cuántos ATRs rompió el canal."""
    upper = candles["high"].rolling(lookback).max().shift()
    lower = candles["low"].rolling(lookback).min().shift()
    close = candles["close"]
    long_entry = close > upper
    short_entry = close < lower
    direction = np.select([long_entry, short_entry], [LONG, SHORT], default=FLAT)
    breakout = np.where(long_entry, close - upper, lower - close)
    score = (pd.Series(breakout, index=candles.index) / features["atr"]).round(3)
    reason = np.select(
        [long_entry, short_entry],
        [f"cierre sobre el máximo de {lookback} velas", f"cierre bajo el mínimo de {lookback} velas"],
        default="",
    )
    signals = pd.DataFrame({"direction": direction, "score": score, "reason": reason}, index=candles.index)
    return signals[signals["direction"] != FLAT]


def daily_regime(candles: pd.DataFrame, ema_days: int = 50) -> pd.Series:
    """+1 si el cierre diario de AYER estaba sobre su EMA de `ema_days` días, -1 si estaba debajo.

    Se usa el día anterior completo: durante el día D solo se conoce el cierre de D-1.
    El resultado se alinea al índice de `candles` (cualquier temporalidad intradía).
    """
    daily_close = candles["close"].resample("1D").last().dropna()
    trend = np.sign(daily_close - ema(daily_close, ema_days)).shift(1)
    return trend.reindex(candles.index.floor("D")).set_axis(candles.index)


def apply_regime(signals: pd.DataFrame, regime: pd.Series) -> pd.DataFrame:
    """Deja solo las señales a favor de la tendencia diaria."""
    return signals[signals["direction"] == regime.reindex(signals.index)]
