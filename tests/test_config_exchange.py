from dataclasses import replace

import pytest

from tradebot.config import DEFAULT_SETTINGS_PATH, ExchangeCredentials, load_settings
from tradebot.exchange import create_exchange, market_symbol


def test_market_symbol():
    assert market_symbol("BTC", "USDT", "spot") == "BTC/USDT"
    assert market_symbol("BTC", "USDT", "swap") == "BTC/USDT:USDT"


def test_default_settings_load():
    settings = load_settings()
    assert settings.bot.exchange in ("bybit", "binance")
    assert settings.ai.daily_call_limit > 0


def test_invalid_market_type_fails(tmp_path):
    bad = tmp_path / "settings.toml"
    text = DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8").replace('"swap"', '"margin"', 1)
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="market_type"):
        load_settings(bad)


@pytest.mark.parametrize("exchange", ["bybit", "binance"])
@pytest.mark.parametrize("market_type", ["spot", "swap"])
def test_exchange_is_always_testnet(exchange, market_type):
    bot = replace(load_settings().bot, exchange=exchange, market_type=market_type)
    client = create_exchange(bot, ExchangeCredentials(api_key="k", secret="s"))
    assert client.options["defaultType"] == market_type
    assert client.isSandboxModeEnabled
