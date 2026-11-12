"""Resumen mensual del bot de tendencia: ¿se comporta como el backtest?

Tres comprobaciones:
1. Rendimiento del mes y acumulado, contra comprar y mantener BTC en los mismos días.
2. Peor caída desde el máximo, contra la del backtest.
3. Fidelidad: el motor del backtest, corrido sobre los mismos días, debe terminar con el mismo capital
   que la cuenta en vivo. Si difieren, la cuenta en vivo no está haciendo lo que se probó.

El scheduler de tradebot.run lo envía el día 1 de cada mes con el mes anterior.

Uso manual:
    python -m tradebot.live.trend_report                         # mes anterior, por Telegram
    python -m tradebot.live.trend_report --mes 2026-11 --sin-enviar
"""

import argparse
import logging
from dataclasses import dataclass, replace

import pandas as pd

from tradebot import db
from tradebot.backtest.data import load_market
from tradebot.backtest.trend import daily_closes, simulate, target_weights
from tradebot.config import Settings, load_settings
from tradebot.notify import Card, create_notifier, failure_card

log = logging.getLogger(__name__)

# Backtest walk-forward 2022–2026 de la versión largo/corto (docs/investigacion.md).
BACKTEST_ANNUAL = 0.174
BACKTEST_MAX_DRAWDOWN = -0.336
FIDELITY_TOLERANCE = 0.01   # más de 1% de diferencia con el backtest es una alarma
MIN_DAYS_TO_JUDGE = 90      # antes de esto, cualquier resultado es mayormente ruido
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]


@dataclass(frozen=True)
class MonthlyReport:
    month: pd.Period
    first_day: pd.Timestamp       # primer día del mes con la cuenta activa
    last_day: pd.Timestamp        # último cierre diario procesado dentro del mes
    days_live: int                # días desde que arrancó la cuenta
    equity: float
    month_return: float
    btc_month: float | None
    total_return: float
    btc_total: float | None
    max_drawdown: float           # peor caída desde el máximo, de todo el historial (negativa)
    replay_equity: float          # capital que da el motor del backtest en los mismos días
    rebalances: int               # días con rebalanceo dentro del mes

    @property
    def fidelity_gap(self) -> float:
        return self.equity / self.replay_equity - 1

    @property
    def faithful(self) -> bool:
        return abs(self.fidelity_gap) <= FIDELITY_TOLERANCE

    def summary(self) -> str:
        return (f"tendencia {self.month}: mes {self.month_return:+.1%}, acumulado {self.total_return:+.1%}, "
                f"caída máx {self.max_drawdown:.1%}, fidelidad {self.fidelity_gap:+.2%}")

    def card(self) -> Card:
        def vs_btc(value: float, btc: float | None) -> str:
            return f"{value:+.1%}" + (f"  (BTC {btc:+.1%})" if btc is not None else "")

        rows = (
            ("Periodo", f"{self.first_day:%d/%m} → {self.last_day:%d/%m}"),
            ("Mes", vs_btc(self.month_return, self.btc_month)),
            ("Acumulado", vs_btc(self.total_return, self.btc_total) + f"  en {self.days_live} días"),
            ("Capital", f"{self.equity:,.2f} USDT"),
            ("Peor caída", f"{self.max_drawdown:.1%}  (backtest {BACKTEST_MAX_DRAWDOWN:.1%})"),
            ("Rebalanceos", f"{self.rebalances} en el mes"),
            ("Fidelidad", ("✓ igual al backtest" if self.faithful else "⚠ distinto al backtest")
             + f"  ({self.fidelity_gap:+.2%})"),
        )
        note = f"Backtest 2022–2026: {BACKTEST_ANNUAL:+.1%} al año, caída máx {BACKTEST_MAX_DRAWDOWN:.1%}."
        if self.days_live < MIN_DAYS_TO_JUDGE:
            note += f" Con menos de {MIN_DAYS_TO_JUDGE} días, el resultado es mayormente ruido."
        if not self.faithful:
            note += " La cuenta en vivo no coincide con el backtest: revisar días saltados o datos corregidos."
        title = f"Resumen mensual tendencia · {MONTHS[self.month.month - 1]} {self.month.year}"
        return Card("🗓", title, rows, note)


def max_drawdown(equity: pd.Series, initial: float) -> float:
    """Peor caída desde el máximo; el capital inicial cuenta como primer máximo."""
    peak = equity.cummax().clip(lower=initial)
    return float((equity / peak - 1).min()) if len(equity) else 0.0


def build_report(month: pd.Period, daily: pd.Series, snapshots: pd.Series, btc: pd.Series | None,
                 replay: pd.Series, rebalance_days: pd.DatetimeIndex, initial: float) -> MonthlyReport | None:
    """`daily` y `replay`: capital al cierre de cada día (índice = día). `snapshots`: capital horario.

    Devuelve None si la cuenta no tuvo días cerrados en ese mes."""
    start, end = month.start_time.tz_localize("UTC"), month.end_time.tz_localize("UTC")
    in_month = daily[(daily.index >= start) & (daily.index <= end)]
    if in_month.empty:
        return None
    first, last = in_month.index[0], in_month.index[-1]
    before = daily[daily.index < start]
    base = float(before.iloc[-1]) if len(before) else initial

    def btc_return(since: pd.Timestamp) -> float | None:
        # Desde el cierre en que arrancó la cuenta (o el último del mes anterior) hasta el último del mes.
        if btc is None or since not in btc.index or last not in btc.index:
            return None
        return float(btc[last] / btc[since] - 1)

    month_base_day = before.index[-1] if len(before) else daily.index[0]
    return MonthlyReport(
        month=month, first_day=first, last_day=last,
        days_live=len(daily[daily.index <= last]),
        equity=float(daily[last]),
        month_return=float(daily[last]) / base - 1,
        btc_month=btc_return(month_base_day),
        total_return=float(daily[last]) / initial - 1,
        btc_total=btc_return(daily.index[0]),
        max_drawdown=max_drawdown(snapshots[snapshots.index <= last + pd.Timedelta(days=1)], initial),
        replay_equity=float(replay[last]),
        rebalances=int(((rebalance_days >= first) & (rebalance_days <= last)).sum()),
    )


def load_report(settings: Settings, month: pd.Period) -> MonthlyReport | None:
    instance, initial = settings.trend.instance, settings.trend.initial_capital
    with db.connect() as conn:
        rows = conn.execute("select ts, equity from equity_snapshots where instance = %s order by ts", (instance,)).fetchall()
        last_day = conn.execute("select last_day from paper_accounts where instance = %s", (instance,)).fetchone()
        trade_ts = [r[0] for r in conn.execute(
            "select distinct ts from paper_trades where instance = %s", (instance,)).fetchall()]
    if not rows or last_day is None:
        return None
    snapshots = pd.Series({pd.Timestamp(ts): float(eq) for ts, eq in rows}).sort_index()
    # El cierre del día D se guarda a las 00:00 del D+1 (ver PaperStore.save_day).
    last = pd.Timestamp(last_day[0], tz="UTC")
    daily = snapshots[snapshots.index.hour == 0]
    daily.index = daily.index - pd.Timedelta(days=1)
    daily = daily[daily.index <= last]

    closes, funding = daily_closes(load_market(settings))
    targets = target_weights(closes, settings.trend.long_only)
    costs = replace(settings.backtest, initial_capital=initial)
    replay = simulate(closes.loc[:last], funding.loc[:last], targets.loc[:last], costs, daily.index[0]).equity
    btc_col = next((c for c in closes.columns if c.startswith("BTC/")), None)
    rebalance_days = pd.DatetimeIndex([pd.Timestamp(ts) - pd.Timedelta(days=1) for ts in trade_ts])
    return build_report(month, daily, snapshots, closes[btc_col] if btc_col else None, replay, rebalance_days, initial)


def send_monthly(settings: Settings, month: pd.Period | None = None, send: bool = True) -> int:
    """Lo que corre el scheduler el día 1: resumen del mes anterior por Telegram."""
    month = month or (pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M") - 1)
    notifier = create_notifier(source=settings.trend.instance)
    try:
        report = load_report(settings, month)
    except Exception as exc:  # noqa: BLE001 - un resumen fallido no debe tumbar el scheduler
        log.exception("tendencia: no se pudo armar el resumen mensual")
        if send:
            notifier.send("warning", f"resumen mensual falló: {exc}", failure_card("el resumen mensual", exc))
        return 1
    if report is None:
        log.info("tendencia: sin días cerrados en %s, no hay resumen", month)
        return 0
    log.info(report.summary())
    if send:
        notifier.send("info", report.summary(), report.card())
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Resumen mensual del bot de tendencia")
    parser.add_argument("--mes", help="mes a resumir, AAAA-MM (por defecto, el anterior)")
    parser.add_argument("--sin-enviar", action="store_true", help="solo mostrarlo en la terminal")
    args = parser.parse_args(argv)
    month = pd.Period(args.mes, freq="M") if args.mes else None
    return send_monthly(load_settings(), month, send=not args.sin_enviar)


if __name__ == "__main__":
    raise SystemExit(main())
