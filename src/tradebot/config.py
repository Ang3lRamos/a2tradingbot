import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ExchangeName = Literal["bybit", "binance"]
MarketType = Literal["spot", "swap"]

# TRADEBOT_SETTINGS permite indicar otra ruta (p. ej. dentro de un contenedor).
DEFAULT_SETTINGS_PATH = Path(os.getenv("TRADEBOT_SETTINGS") or Path(__file__).resolve().parents[2] / "config" / "settings.toml")


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
    fallback: str = "veto"
    eval_daily_call_limit: int = 40


@dataclass(frozen=True)
class RiskSettings:
    risk_per_trade: float
    stop_atr_multiple: float
    take_profit_r: float
    max_open_positions: int
    max_daily_loss: float
    max_drawdown: float


@dataclass(frozen=True)
class StrategySettings:
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_long_trigger: float
    rsi_short_trigger: float
    atr_period: int
    variant: str = "pullback-1h"


@dataclass(frozen=True)
class BacktestSettings:
    initial_capital: float
    fee_rate: float
    slippage: float
    oos_start: str
    # Inicio del periodo in-sample. Fijo para que agregar historia vieja no cambie los resultados ya
    # documentados; vacío = desde la primera vela disponible (más el calentamiento).
    is_start: str = ""


@dataclass(frozen=True)
class TrendSettings:
    """Bot de tendencia en cuenta virtual (ver docs/investigacion.md)."""
    instance: str = "tendencia-ls"
    initial_capital: float = 5000.0
    long_only: bool = False


@dataclass(frozen=True)
class Settings:
    bot: BotSettings
    ai: AISettings
    risk: RiskSettings
    strategy: StrategySettings
    backtest: BacktestSettings
    trend: TrendSettings = TrendSettings()


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
        strategy=StrategySettings(**raw["strategy"]),
        backtest=BacktestSettings(**raw["backtest"]),
        trend=TrendSettings(**raw.get("trend", {})),
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
    """Llave HMAC (`<EXCHANGE>_API_SECRET`) o Ed25519 (`<EXCHANGE>_PRIVATE_KEY_PATH`, archivo PEM).

    Con Ed25519 ccxt firma con la llave privada, que se lee de un archivo fuera del repo.
    """
    load_dotenv()
    prefix = exchange.upper()
    key_path = os.getenv(f"{prefix}_PRIVATE_KEY_PATH")
    if key_path:
        path = Path(key_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"{prefix}_PRIVATE_KEY_PATH apunta a un archivo que no existe: {path}")
        secret = path.read_text(encoding="utf-8").strip()
        if "PRIVATE KEY" not in secret:
            raise RuntimeError(f"{path} no es una llave privada PEM (debe empezar con -----BEGIN PRIVATE KEY-----)")
    else:
        secret = _require_env(f"{prefix}_API_SECRET")
    return ExchangeCredentials(api_key=_require_env(f"{prefix}_API_KEY"), secret=secret)


def load_database_url() -> str:
    load_dotenv()
    return _require_env("DATABASE_URL")
