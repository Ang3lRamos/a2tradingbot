"""Resultado de cada señal por separado, como si fuera la única operación.

Sirve para medir un filtro (como la IA) sin que se mezcle con efectos de cartera: posiciones
llenas, límites diarios o el kill switch. Usa el mismo motor y los mismos costos que el backtest.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from tradebot.backtest.data import to_arrays
from tradebot.backtest.engine import run_backtest
from tradebot.config import BacktestSettings, RiskSettings

MAX_BARS = 180  # 30 días en velas de 4h; si sigue abierta, se cierra ahí


def signal_outcome(candles: pd.DataFrame, atr: pd.Series, funding: pd.Series, signal: pd.DataFrame,
                   risk: RiskSettings, costs: BacktestSettings, timeframe: str, trailing_stop: bool) -> float:
    """R múltiplo neto de una sola señal (fila de `signal`, índice = vela de la señal)."""
    position = candles.index.get_loc(signal.index[0])
    window = candles.index[position:position + MAX_BARS + 1]
    if len(window) < 2:
        return np.nan
    isolated = replace(risk, max_open_positions=1, max_daily_loss=1.0, max_drawdown=1.0)
    data = to_arrays(candles, atr, signal, funding, window, timeframe)
    trades = run_backtest(window, {"X": data}, isolated, costs, trailing_stop=trailing_stop).trades
    return float(trades.iloc[0]["r_multiple"]) if not trades.empty else np.nan
