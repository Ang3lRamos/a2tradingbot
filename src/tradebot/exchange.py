import ccxt

from tradebot.config import BotSettings, ExchangeCredentials, MarketType


def market_symbol(base: str, quote: str, market_type: MarketType) -> str:
    """Símbolo en formato ccxt: 'BTC/USDT' en spot, 'BTC/USDT:USDT' en perpetuos lineales."""
    if market_type == "spot":
        return f"{base}/{quote}"
    return f"{base}/{quote}:{quote}"


def create_exchange(bot: BotSettings, credentials: ExchangeCredentials) -> ccxt.Exchange:
    exchange_class = getattr(ccxt, bot.exchange)
    exchange = exchange_class(
        {
            "apiKey": credentials.api_key,
            "secret": credentials.secret,
            "enableRateLimit": True,
            "options": {"defaultType": bot.market_type},
        }
    )
    # Siempre testnet en esta etapa del proyecto: no hay camino para operar con dinero real.
    exchange.set_sandbox_mode(True)
    return exchange
