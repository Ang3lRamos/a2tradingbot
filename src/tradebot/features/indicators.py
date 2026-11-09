"""Indicadores técnicos sobre velas OHLCV.

Cada valor en la fila t usa solo velas hasta t inclusive (sin mirar al futuro).
RSI y ATR usan el suavizado de Wilder, igual que TradingView y la mayoría de plataformas.
"""

import pandas as pd

from tradebot.config import StrategySettings

BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder(-delta.clip(upper=0), period)
    rs = gain / loss
    result = 100 - 100 / (1 + rs)
    # Sin pérdidas en la ventana el RSI es 100 (rs infinito).
    return result.where(loss != 0, 100.0).where(gain.notna())


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift()
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return _wilder(true_range, period)


def bollinger(close: pd.Series, period: int = BOLLINGER_PERIOD, n_std: float = BOLLINGER_STD) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper, lower = mid + n_std * std, mid - n_std * std
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower,
                         "bb_width": (upper - lower) / mid})


def compute_features(candles: pd.DataFrame, settings: StrategySettings) -> pd.DataFrame:
    """`candles` con índice ts y columnas open, high, low, close, volume."""
    close = candles["close"]
    features = pd.DataFrame(index=candles.index)
    features["ema_fast"] = ema(close, settings.ema_fast)
    features["ema_slow"] = ema(close, settings.ema_slow)
    features["rsi"] = rsi(close, settings.rsi_period)
    features["atr"] = atr(candles["high"], candles["low"], close, settings.atr_period)
    features["atr_pct"] = features["atr"] / close
    return features.join(bollinger(close))
