"""Carga y preparación de datos para el backtest: velas por temporalidad, funding y arreglos alineados."""

from dataclasses import dataclass

import pandas as pd

from tradebot import db
from tradebot.backtest.engine import SymbolData
from tradebot.config import Settings
from tradebot.exchange import market_symbol

OHLCV_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


@dataclass(frozen=True)
class MarketData:
    candles: pd.DataFrame  # velas de 1h, índice ts
    funding: pd.Series  # tasa por instante de cobro, alineada a la hora en punto


def load_market(settings: Settings) -> dict[str, MarketData]:
    bot = settings.bot
    symbols = [market_symbol(base, bot.quote, bot.market_type) for base in bot.bases]
    market = {}
    with db.connect() as conn:
        for symbol in symbols:
            funding = db.load_context(conn, symbol, "funding_rate")
            # Binance a veces marca el funding unos milisegundos después de la hora en punto.
            funding.index = pd.DatetimeIndex(funding.index).floor("h")
            market[symbol] = MarketData(db.load_candles(conn, symbol, bot.timeframe), funding.groupby(level=0).sum())
    return market


def resample_candles(candles: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Agrupa velas de 1h en `timeframe` (p. ej. '4h'). Descarta la última si está incompleta."""
    if timeframe == "1h":
        return candles
    grouped = candles.resample(timeframe, label="left", closed="left")
    expected = pd.Timedelta(timeframe) // pd.Timedelta("1h")
    resampled = grouped.agg(OHLCV_AGG)
    return resampled[grouped["close"].count() == expected]


def to_arrays(candles: pd.DataFrame, atr: pd.Series, signals: pd.DataFrame, funding: pd.Series,
              index: pd.DatetimeIndex, timeframe: str) -> SymbolData:
    candles = candles.reindex(index)
    signals = signals.reindex(index)
    # El funding cobrado dentro de una vela se aplica en esa vela.
    funding = funding.resample(timeframe, label="left", closed="left").sum() if timeframe != "1h" else funding
    return SymbolData(
        open=candles["open"].to_numpy(), high=candles["high"].to_numpy(), low=candles["low"].to_numpy(),
        close=candles["close"].to_numpy(), atr=atr.reindex(index).to_numpy(),
        signal=signals["direction"].fillna(0).to_numpy(), score=signals["score"].fillna(0).to_numpy(),
        funding=funding.reindex(index).fillna(0).to_numpy(),
    )


def period_index(index: pd.DatetimeIndex, start: pd.Timestamp, oos_start: pd.Timestamp, period: str) -> pd.DatetimeIndex:
    index = index[index >= start]
    if period == "is":
        return index[index < oos_start]
    if period == "oos":
        return index[index >= oos_start]
    return index


def common_index(frames: list[pd.DataFrame]) -> pd.DatetimeIndex:
    index = frames[0].index
    for frame in frames[1:]:
        index = index.intersection(frame.index)
    return index
