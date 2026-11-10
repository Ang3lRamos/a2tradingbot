"use client";

import { base } from "@/lib/binance";
import { num, pct, price, tone } from "@/lib/format";
import type { Live, Market, Position, Trend } from "@/lib/types";

import { CandleChart } from "./candle-chart";
import { useLiveMarket, type Ticker } from "./live-market";
import { Empty, Panel, Stat } from "./panel";

const direction = (side: Position["lado"]) => (side === "long" ? 1 : -1);

/** P&L no realizado neto de la comisión de entrada. */
function unrealized(p: Position, px: number): number {
  return direction(p.lado) * p.cantidad * (px - p.entrada) - (p.comisiones ?? 0);
}

/**
 * Capital de la cuenta de rupturas al precio de ahora. El capital publicado ya trae el no realizado
 * al cierre de la última vela de 1h (`reference`); se suma solo lo que se movió desde entonces.
 */
export function liveBreakoutEquity(live: Live | null, tickers: Record<string, Ticker>, reference: Record<string, number>): number | null {
  if (live?.capital_actual == null) return null;
  return live.capital_actual + live.posiciones_abiertas.reduce((sum, p) => {
    const coin = base(p.simbolo);
    const px = tickers[coin]?.price;
    const ref = reference[coin];
    return px == null || ref == null ? sum : sum + direction(p.lado) * p.cantidad * (px - ref);
  }, 0);
}

/** Capital de la cuenta virtual de tendencia: el publicado más lo que se movió cada moneda desde entonces. */
export function liveTrendEquity(trend: Trend | null | undefined, tickers: Record<string, Ticker>): number | null {
  if (!trend) return null;
  return trend.capital_actual + trend.pesos.reduce((sum, w) => {
    const px = tickers[base(w.simbolo)]?.price;
    return px == null || w.cantidad === 0 ? sum : sum + w.cantidad * px - w.valor;
  }, 0);
}

export function LiveEquity({ source, live, trend, markets = [] }: {
  source: "rupturas" | "tendencia";
  live?: Live | null;
  trend?: Trend | null;
  markets?: Market[];
}) {
  const { tickers } = useLiveMarket();
  const reference = Object.fromEntries(markets.map((m) => [base(m.simbolo), m.precio]));
  const value = source === "rupturas" ? liveBreakoutEquity(live ?? null, tickers, reference) : liveTrendEquity(trend, tickers);
  return <>{num(value)}</>;
}

export function PositionsPanel({ live, trend }: { live: Live | null; trend: Trend | null | undefined }) {
  const open = live?.posiciones_abiertas ?? [];
  const held = (trend?.pesos ?? []).filter((w) => w.cantidad !== 0);
  return (
    <Panel title="Posiciones abiertas" aside={`${open.length + held.length} en total`}>
      <h3 className="border-b border-line bg-panel-raised px-3 py-1 text-[11px] uppercase tracking-[0.08em] text-ink-faint">
        Rupturas · Binance Demo
      </h3>
      {open.length === 0 ? <Empty>Sin posiciones abiertas: espera una ruptura de canal en 4h.</Empty> : open.map((p) => <BreakoutCard key={p.id} p={p} />)}
      <h3 className="border-y border-line bg-panel-raised px-3 py-1 text-[11px] uppercase tracking-[0.08em] text-ink-faint">
        Tendencia L/S · cuenta virtual
      </h3>
      {held.length === 0 ? <Empty>Sin exposición.</Empty> : <TrendRows trend={trend!} />}
    </Panel>
  );
}

function BreakoutCard({ p }: { p: Position }) {
  const { tickers, select, selected } = useLiveMarket();
  const coin = base(p.simbolo);
  const ticker = tickers[coin];
  const px = ticker?.price ?? null;
  const pnl = px != null ? unrealized(p, px) : null;
  const risk = p.riesgo != null ? p.riesgo * p.cantidad : null;
  const toStop = px != null ? (direction(p.lado) * (px - p.stop)) / px : null;
  const hours = ticker ? (ticker.at - new Date(p.abierta).getTime()) / 3_600_000 : null;
  const long = p.lado === "long";

  return (
    <article className={`border-b border-line ${selected === coin ? "bg-panel-raised/40" : ""}`}>
      <button onClick={() => select(coin)} className="flex w-full items-center gap-2 px-3 pt-2 text-left" title="Ver en el gráfico principal">
        <span className="font-medium">{coin}</span>
        <span className={`text-[11px] font-medium uppercase ${long ? "text-up" : "text-down"}`}>{long ? "▲ long" : "▼ short"}</span>
        <span className="num text-[11px] text-ink-faint">{num(p.cantidad, 4)} · x{num(p.tamano_ia, 2)} IA</span>
        <span className="num ml-auto text-[11px] text-ink-faint">{hours != null ? (hours < 48 ? `${hours.toFixed(1)} h` : `${(hours / 24).toFixed(1)} d`) : ""}</span>
      </button>
      <div className="grid grid-cols-3 [&>*:not(:last-child)]:border-r [&>*]:border-line">
        <Stat label="Precio" value={px != null ? price(px) : "—"} sub={`entrada ${price(p.entrada)}`} />
        <Stat label="P&L" value={num(pnl, 2, true)} valueClass={tone(pnl)}
          sub={pnl != null && risk ? `${num(pnl / risk, 2, true)} R` : "USDT"} />
        <Stat label="Al stop" value={pct(toStop, 1, false)} valueClass={toStop != null && toStop < 0.01 ? "text-warn" : ""}
          sub={price(p.stop)} />
      </div>
      <div className="h-[120px] border-t border-line">
        <CandleChart symbol={p.simbolo} interval="1h" bars={72} compact
          lines={[{ price: p.entrada, label: "Entrada", tone: "bot" }, { price: p.stop, label: "Stop", tone: "down", dashed: true }]}
          markers={[{ at: p.abierta, side: p.lado, kind: "entry" }]} />
      </div>
    </article>
  );
}

function TrendRows({ trend }: { trend: Trend }) {
  const { tickers, select } = useLiveMarket();
  const live = liveTrendEquity(trend, tickers) ?? trend.capital_actual;
  return (
    <table className="w-full text-[12px]">
      <thead className="text-left text-[11px] text-ink-muted">
        <tr>
          <th className="px-3 py-1.5 font-normal">Par</th>
          <th className="text-right font-normal">Valor</th>
          <th className="text-right font-normal">Peso</th>
          <th className="pr-3 text-right font-normal" title="Desde la última valoración publicada (cada hora)">Δ hora</th>
        </tr>
      </thead>
      <tbody className="num">
        {trend.pesos.filter((w) => w.cantidad !== 0).map((w) => {
          const coin = base(w.simbolo);
          const px = tickers[coin]?.price;
          const value = px != null ? w.cantidad * px : w.valor;
          const change = value - w.valor;
          const long = w.cantidad > 0;
          return (
            <tr key={w.simbolo} onClick={() => select(coin)} className="cursor-pointer border-t border-line hover:bg-panel-raised">
              <td className="px-3 py-1.5">
                <span className="font-sans font-medium">{coin}</span>{" "}
                <span className={`font-sans text-[11px] uppercase ${long ? "text-up" : "text-down"}`}>{long ? "▲ long" : "▼ short"}</span>
              </td>
              <td className="text-right">{num(Math.abs(value))}</td>
              <td className="text-right">{pct(value / live, 1)}</td>
              <td className={`pr-3 text-right ${tone(change)}`}>{num(change, 2, true)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
