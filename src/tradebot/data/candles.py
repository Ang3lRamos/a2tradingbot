from collections.abc import Iterator

import ccxt

from tradebot.data.paginate import paginate

# Fila OHLCV de ccxt: [ts_ms, open, high, low, close, volume]
Candle = list[float]

PAGE_SIZE = 1000


def timeframe_ms(timeframe: str) -> int:
    return ccxt.Exchange.parse_timeframe(timeframe) * 1000


def last_closed_open_ms(now_ms: int, timeframe: str) -> int:
    """Apertura de la vela en curso: toda vela con ts menor a este valor ya cerró."""
    step = timeframe_ms(timeframe)
    return now_ms - now_ms % step


def fetch_closed_candles(
    exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int, now_ms: int
) -> Iterator[list[Candle]]:
    """Velas cerradas desde `since_ms`, por páginas. La vela en curso nunca se guarda a medias."""
    return paginate(
        fetch_page=lambda cursor: exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=PAGE_SIZE),
        ts_of=lambda candle: int(candle[0]),
        since_ms=since_ms,
        until_ms=last_closed_open_ms(now_ms, timeframe),
        step_ms=timeframe_ms(timeframe),
    )
