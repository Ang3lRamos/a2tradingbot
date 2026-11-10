"use client";

import { base } from "@/lib/binance";
import { num, pct, tone } from "@/lib/format";
import type { Live, Position, Trend } from "@/lib/types";

import { useLiveMarket } from "./live-market";
import { liveTrendEquity, unrealized } from "./positions-panel";

/** Resultado de una operación cerrada en múltiplos del riesgo inicial. */
export function rMultiple(p: Position): number | null {
  if (p.pnl == null || !p.riesgo) return null;
  return p.pnl / (p.riesgo * p.cantidad);
}

/** Franja de resumen: lo abierto, lo cerrado y el total de cada bot, de un vistazo y en vivo. */
export function PnlSummary({ live, trend }: { live: Live | null; trend: Trend | null }) {
  const { tickers } = useLiveMarket();
  const open = live?.posiciones_abiertas ?? [];
  const closed = live?.operaciones_cerradas ?? [];

  const openPnl = open.reduce<number | null>((sum, p) => {
    const px = tickers[base(p.simbolo)]?.price;
    return px == null || sum == null ? null : sum + unrealized(p, px);
  }, 0);
  const closedPnl = closed.reduce((sum, p) => sum + (p.pnl ?? 0), 0);
  const total = openPnl == null ? null : openPnl + closedPnl;
  const wins = closed.filter((p) => (p.pnl ?? 0) > 0).length;
  const losses = closed.length - wins;
  const trendEquity = liveTrendEquity(trend, tickers);
  const trendPnl = trend && trendEquity != null ? trendEquity - trend.capital_inicial : null;

  return (
    <section aria-label="Resumen" className="grid grid-cols-2 border-b border-line bg-panel sm:grid-cols-3 lg:grid-cols-[repeat(5,minmax(0,1fr))_minmax(0,1.2fr)] [&>*]:border-line [&>*]:border-b lg:[&>*]:border-b-0 [&>*:not(:last-child)]:border-r">
      <Cell label="Abiertas · rupturas" value={`${open.length}`}
        sub={open.length ? open.map((p) => `${base(p.simbolo)} ${p.lado === "long" ? "▲" : "▼"}`).join(" · ") : "ninguna"} />
      <Cell label="P&L abierto" value={num(openPnl, 2, true)} valueClass={tone(openPnl)} sub="sin cerrar, en vivo" />
      <Cell label="P&L cerrado" value={num(closedPnl, 2, true)} valueClass={tone(closed.length ? closedPnl : null)}
        sub={`${closed.length} operaciones`} />
      <Cell label="Total rupturas" value={num(total, 2, true)} valueClass={tone(total)} sub="USDT" strong />
      <Cell label="Ganadas / perdidas" value={<><span className="text-up">{wins}</span><span className="text-ink-faint"> / </span><span className="text-down">{losses}</span></>}
        sub={closed.length ? `acierto ${pct(wins / closed.length, 0, false)}` : "acierto —"} />
      <Cell label="Tendencia L/S · total" value={num(trendPnl, 2, true)} valueClass={tone(trendPnl)}
        sub={trend ? `${pct(trendPnl != null ? trendPnl / trend.capital_inicial : null)} · cuenta virtual` : "sin datos"} />
    </section>
  );
}

function Cell({ label, value, sub, valueClass = "", strong = false }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueClass?: string;
  strong?: boolean;
}) {
  return (
    <div className={`min-w-0 px-3 py-2 ${strong ? "bg-panel-raised" : ""}`}>
      <div className="truncate text-[11px] uppercase tracking-[0.06em] text-ink-muted">{label}</div>
      <div className={`num truncate font-medium leading-7 ${strong ? "text-[22px]" : "text-[19px]"} ${valueClass}`}>{value}</div>
      {sub ? <div className="num truncate text-[11px] leading-4 text-ink-faint">{sub}</div> : null}
    </div>
  );
}
