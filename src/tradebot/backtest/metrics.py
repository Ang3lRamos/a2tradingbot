import numpy as np
import pandas as pd

from tradebot.config import BacktestSettings

HOURS_PER_YEAR = 24 * 365


def periods_per_year(index: pd.Index) -> float:
    """Velas por año según la frecuencia real de la serie (1h → 8760, 4h → 2190)."""
    if isinstance(index, pd.DatetimeIndex) and len(index) > 1:
        step_hours = pd.Series(index).diff().median() / pd.Timedelta("1h")
        return HOURS_PER_YEAR / step_hours
    return HOURS_PER_YEAR


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def sharpe(returns: pd.Series) -> float:
    std = returns.std()
    return float(returns.mean() / std * np.sqrt(periods_per_year(returns.index))) if std > 0 else 0.0


def sortino(returns: pd.Series) -> float:
    downside = returns.clip(upper=0)
    downside_dev = np.sqrt((downside**2).mean())
    return float(returns.mean() / downside_dev * np.sqrt(periods_per_year(returns.index))) if downside_dev > 0 else 0.0


def buy_and_hold(close: pd.Series, costs: BacktestSettings) -> pd.Series:
    """Compra en la primera vela y mantiene, con una comisión y slippage de entrada y otra de salida."""
    entry = close.iloc[0] * (1 + costs.slippage)
    qty = costs.initial_capital * (1 - costs.fee_rate) / entry
    equity = qty * close
    exit_cost = equity.iloc[-1] * (costs.fee_rate + costs.slippage)
    equity.iloc[-1] -= exit_cost
    return equity.rename("buy_and_hold")


def summarize(equity: pd.Series, trades: pd.DataFrame) -> dict[str, float]:
    returns = equity.pct_change().dropna()
    summary = {
        "retorno_neto": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "max_drawdown": max_drawdown(equity),
        "sharpe": sharpe(returns),
        "sortino": sortino(returns),
    }
    if trades.empty:
        return summary | {"operaciones": 0}
    wins, losses = trades[trades["net_pnl"] > 0], trades[trades["net_pnl"] <= 0]
    gross_loss = -losses["net_pnl"].sum()
    return summary | {
        "operaciones": len(trades),
        "tasa_acierto": len(wins) / len(trades),
        "ganancia_promedio": float(wins["net_pnl"].mean()) if len(wins) else 0.0,
        "perdida_promedio": float(losses["net_pnl"].mean()) if len(losses) else 0.0,
        "profit_factor": float(wins["net_pnl"].sum() / gross_loss) if gross_loss > 0 else float("inf"),
        "r_promedio": float(trades["r_multiple"].mean()),
        "comisiones": float(trades["fees"].sum()),
        "funding": float(trades["funding"].sum()),
    }
