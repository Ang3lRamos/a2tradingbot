"""Estrategia base, sin IA: seguir la tendencia y entrar cuando termina un retroceso.

Long:  EMA rápida > EMA lenta (tendencia alcista) y el RSI cruza hacia arriba `rsi_long_trigger`.
Short: EMA rápida < EMA lenta (tendencia bajista) y el RSI cruza hacia abajo `rsi_short_trigger`.

La señal se calcula al cierre de la vela t; la entrada ocurre en la apertura de t+1.
Puntaje: separación entre las EMAs medida en ATRs (qué tan clara es la tendencia).
"""

import numpy as np
import pandas as pd

from tradebot.config import StrategySettings

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
