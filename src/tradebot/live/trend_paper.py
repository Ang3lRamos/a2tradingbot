"""Bot de tendencia largo/corto en una cuenta virtual (ver docs/investigacion.md).

Una vez al día, tras el cierre diario (00:00 UTC): cobra el funding del día, valora la cartera y
rebalancea hacia los pesos objetivo de `backtest.trend`, con los mismos costos que el backtest.
No manda órdenes al exchange: la cuenta demo es de una posición por moneda y chocaría con el bot de
rupturas. Si el bot estuvo apagado, procesa los días pendientes en orden.

Uso manual:
    python -m tradebot.live.trend_paper
"""

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from tradebot import db
from tradebot.backtest.data import load_market
from tradebot.backtest.trend import REBALANCE_BAND, daily_closes, target_weights
from tradebot.config import BacktestSettings, Settings, load_settings
from tradebot.notify import Card, coin, create_notifier, failure_card

log = logging.getLogger(__name__)


@dataclass
class Account:
    cash: float
    qty: dict[str, float] = field(default_factory=dict)
    last_day: date | None = None


@dataclass(frozen=True)
class Trade:
    symbol: str
    qty: float
    price: float
    cost: float
    weight_before: float
    weight_after: float


@dataclass(frozen=True)
class DayResult:
    day: date
    equity: float
    weights: dict[str, float]
    trades: list[Trade]

    def summary(self) -> str:
        weights = ", ".join(f"{coin(s)} {w:+.0%}" for s, w in self.weights.items())
        changes = "; ".join(f"{coin(t.symbol)} {t.weight_before:+.0%}→{t.weight_after:+.0%}" for t in self.trades)
        return (f"{self.day}: capital {self.equity:,.2f} | pesos {weights}"
                + (f" | rebalanceo: {changes}" if self.trades else " | sin cambios"))

    def card(self, initial_capital: float) -> Card:
        rows = [("Capital", f"{self.equity:,.2f} USDT ({self.equity / initial_capital - 1:+.1%})")]
        traded = {t.symbol: t for t in self.trades}
        for symbol, weight in self.weights.items():
            trade = traded.get(symbol)
            change = f"{trade.weight_before:+.0%} → {trade.weight_after:+.0%}" if trade else f"{weight:+.0%} (igual)"
            rows.append((coin(symbol), change))
        cost = sum(t.cost for t in self.trades)
        return Card("🔄", f"Rebalanceo tendencia · {self.day}", tuple(rows), f"Costo de las operaciones: {cost:,.2f} USDT")


def step_day(account: Account, close: pd.Series, prev_close: pd.Series | None, funding: pd.Series,
             target: pd.Series, costs: BacktestSettings) -> tuple[float, list[Trade]]:
    """Procesa un cierre diario: funding, valoración y rebalanceo. Devuelve el capital tras costos."""
    if prev_close is not None:
        # Funding del día sobre la exposición que venía del cierre anterior (los largos pagan si es positivo).
        account.cash -= sum(q * prev_close[s] * funding.get(s, 0.0) for s, q in account.qty.items())
    equity = account.cash + sum(q * close[s] for s, q in account.qty.items())
    trades = []
    for symbol, weight in target.items():
        current = account.qty.get(symbol, 0.0) * close[symbol] / equity
        change = weight - current
        if abs(change) <= REBALANCE_BAND:
            continue
        qty = change * equity / close[symbol]
        cost = abs(change) * equity * (costs.fee_rate + costs.slippage)
        account.cash -= qty * close[symbol] + cost
        account.qty[symbol] = account.qty.get(symbol, 0.0) + qty
        trades.append(Trade(symbol, qty, float(close[symbol]), cost, current, float(weight)))
    return account.cash + sum(q * close[s] for s, q in account.qty.items()), trades


class PaperStore:
    def __init__(self, conn, instance: str):
        self.conn, self.instance = conn, instance

    def load(self) -> Account | None:
        row = self.conn.execute("select cash, last_day from paper_accounts where instance = %s", (self.instance,)).fetchone()
        if row is None:
            return None
        qty = dict(self.conn.execute("select symbol, qty from paper_holdings where instance = %s", (self.instance,)).fetchall())
        return Account(float(row[0]), {s: float(q) for s, q in qty.items()}, row[1])

    def save_day(self, account: Account, day: date, equity: float, trades: list[Trade]) -> None:
        """Todo el día en una transacción: si falla a la mitad, el día se reprocesa completo."""
        ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)  # el cierre del día D es a las 00:00 del D+1
        with self.conn.transaction():
            self.conn.execute(
                "insert into paper_accounts (instance, cash, last_day) values (%s, %s, %s) "
                "on conflict (instance) do update set cash = excluded.cash, last_day = excluded.last_day",
                (self.instance, account.cash, day))
            for symbol, qty in account.qty.items():
                self.conn.execute(
                    "insert into paper_holdings (instance, symbol, qty) values (%s, %s, %s) "
                    "on conflict (instance, symbol) do update set qty = excluded.qty", (self.instance, symbol, qty))
            for t in trades:
                self.conn.execute(
                    "insert into paper_trades (instance, ts, symbol, qty, price, cost, weight_before, weight_after) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (self.instance, ts, t.symbol, t.qty, t.price, t.cost, t.weight_before, t.weight_after))
            self.conn.execute(
                "insert into equity_snapshots (instance, ts, equity) values (%s, %s, %s) "
                "on conflict (instance, ts) do update set equity = excluded.equity", (self.instance, ts, equity))


def mark_to_market(settings: Settings) -> float | None:
    """Registra el capital de la cuenta virtual al último cierre de 1h (para la curva horaria del dashboard)."""
    with db.connect() as conn:
        store = PaperStore(conn, settings.trend.instance)
        account = store.load()
        if account is None:
            return None
        equity, last_ts = account.cash, None
        for symbol, qty in account.qty.items():
            ts, close = conn.execute("select ts, close from candles where symbol = %s and timeframe = %s "
                                     "order by ts desc limit 1", (symbol, settings.bot.timeframe)).fetchone()
            equity += qty * float(close)
            last_ts = ts if last_ts is None else min(last_ts, ts)
        if last_ts is None:
            return equity
        # Mismo instante que marca el cierre de esa vela. El rebalanceo diario sobrescribe el de las 00:00 con su valor tras costos.
        conn.execute("insert into equity_snapshots (instance, ts, equity) values (%s, %s, %s) "
                     "on conflict (instance, ts) do nothing", (settings.trend.instance, last_ts + pd.Timedelta(hours=1), equity))
        conn.commit()
        return equity


def pending_days(closes: pd.DataFrame, last_day: date | None) -> list[pd.Timestamp]:
    """Días cerrados por procesar. La primera vez solo el último: la cuenta arranca hoy, no en el pasado."""
    complete = closes.dropna().index
    if last_day is None:
        return list(complete[-1:])
    return [d for d in complete if d.date() > last_day]


def run_daily(settings: Settings) -> list[DayResult]:
    trend = settings.trend
    closes, funding = daily_closes(load_market(settings))
    targets = target_weights(closes, trend.long_only)
    results = []
    with db.connect() as conn:
        store = PaperStore(conn, trend.instance)
        account = store.load() or Account(trend.initial_capital)
        for day in pending_days(closes, account.last_day):
            position = closes.index.get_loc(day)
            prev = closes.iloc[position - 1] if account.last_day is not None else None
            equity, trades = step_day(account, closes.loc[day], prev, funding.loc[day], targets.loc[day], settings.backtest)
            store.save_day(account, day.date(), equity, trades)
            account.last_day = day.date()
            weights = {s: float(targets.loc[day, s]) for s in closes.columns}
            results.append(DayResult(day.date(), equity, weights, trades))
    for result in results:
        log.info("tendencia %s", result.summary())
    return results


def run_and_notify(settings: Settings) -> int:
    """Lo que corre el scheduler: avisa por Telegram los rebalanceos y cualquier fallo."""
    notifier = create_notifier(source=settings.trend.instance)
    try:
        results = run_daily(settings)
    except Exception as exc:  # noqa: BLE001 - el bot de rupturas sigue aunque este falle
        log.exception("tendencia: el ciclo diario falló")
        notifier.send("critical", f"el ciclo diario falló: {type(exc).__name__}: {str(exc)[:300]}",
                      failure_card("el ciclo diario", exc))
        return 1
    if not results:
        log.warning("tendencia: no hay cierre diario nuevo para procesar")
    for result in results:
        if result.trades:
            notifier.send("warning", result.summary(), result.card(settings.trend.initial_capital))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    return run_and_notify(load_settings())


if __name__ == "__main__":
    raise SystemExit(main())
