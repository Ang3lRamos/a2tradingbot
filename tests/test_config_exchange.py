from dataclasses import replace

import pytest

from tradebot.config import DEFAULT_SETTINGS_PATH, ExchangeCredentials, load_settings
from tradebot.exchange import create_exchange, is_paper, market_symbol


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
    assert is_paper(client)
    hosts = " ".join(str(url) for url in client.urls["api"].values())
    assert "testnet" in hosts or "demo" in hosts


def test_ed25519_credentials_from_file(tmp_path, monkeypatch):
    from tradebot.config import load_exchange_credentials

    pem = tmp_path / "id_ed25519"
    pem.write_text("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_PRIVATE_KEY_PATH", str(pem))
    credentials = load_exchange_credentials("binance")
    assert credentials.secret.startswith("-----BEGIN PRIVATE KEY-----")


def test_private_key_path_must_be_pem(tmp_path, monkeypatch):
    from tradebot.config import load_exchange_credentials

    bad = tmp_path / "id_ed25519.pub"
    bad.write_text("MCowBQYDK2VwAyEA", encoding="utf-8")
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_PRIVATE_KEY_PATH", str(bad))
    with pytest.raises(RuntimeError, match="PEM"):
        load_exchange_credentials("binance")
