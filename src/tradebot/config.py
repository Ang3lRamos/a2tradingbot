import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ExchangeName = Literal["bybit", "binance"]
MarketType = Literal["spot", "swap"]

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.toml"


@dataclass(frozen=True)
class BotSettings:
    instance: str
    exchange: ExchangeName
    market_type: MarketType
    quote: str
    bases: list[str]
    timeframe: str


@dataclass(frozen=True)
class AISettings:
    provider: str
    filter_model: str
    decision_model: str
    daily_call_limit: int
    timeout_seconds: int


@dataclass(frozen=True)
class RiskSettings:
    risk_per_trade: float
    stop_atr_multiple: float
    take_profit_r: float
    max_open_positions: int
    max_daily_loss: float
    max_drawdown: float


@dataclass(frozen=True)
class Settings:
    bot: BotSettings
    ai: AISettings
    risk: RiskSettings


@dataclass(frozen=True)
class ExchangeCredentials:
    api_key: str
    secret: str


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> Settings:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    settings = Settings(
        bot=BotSettings(**raw["bot"]),
        ai=AISettings(**raw["ai"]),
        risk=RiskSettings(**raw["risk"]),
    )
    if settings.bot.exchange not in ("bybit", "binance"):
        raise ValueError(f"exchange no soportado: {settings.bot.exchange}")
    if settings.bot.market_type not in ("spot", "swap"):
        raise ValueError(f"market_type debe ser 'spot' o 'swap', no {settings.bot.market_type}")
    return settings


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name} (revisa tu .env)")
    return value


def load_exchange_credentials(exchange: ExchangeName) -> ExchangeCredentials:
    load_dotenv()
    prefix = exchange.upper()
    return ExchangeCredentials(
        api_key=_require_env(f"{prefix}_API_KEY"),
        secret=_require_env(f"{prefix}_API_SECRET"),
    )


def load_database_url() -> str:
    load_dotenv()
    return _require_env("DATABASE_URL")
