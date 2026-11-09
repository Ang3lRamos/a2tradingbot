"use client";

import { useState } from "react";

import { num, pct, price, tone, utc } from "@/lib/format";
import type { Alert, Backtest, Live, Metrics } from "@/lib/types";

import { Empty } from "./panel";

type Tab = "operaciones" | "alertas" | "metricas";

export function BottomTabs({ live, backtestIs, backtestOos }: {
  live: Live | null;
  backtestIs: Backtest | null;
  backtestOos: Backtest | null;
}) {
  const [tab, setTab] = useState<Tab>("operaciones");
  const closed = live?.operaciones_cerradas ?? [];
  const alerts = live?.alertas ?? [];
  const tabs: [Tab, string, number | null][] = [
    ["operaciones", "Operaciones", closed.length],
    ["alertas", "Alertas", alerts.length],
    ["metricas", "Métricas", null],
  ];

  return (
    <section className="flex min-w-0 flex-col bg-panel">
      <header role="tablist" className="flex h-8 shrink-0 items-stretch border-b border-line px-1">
        {tabs.map(([key, label, count]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 border-b-2 px-2.5 text-[11px] uppercase tracking-[0.08em] transition-colors ${tab === key ? "border-series-bot text-ink" : "border-transparent text-ink-muted hover:text-ink"}`}>
            {label}
            {count != null ? <span className="num text-ink-faint">{count}</span> : null}
          </button>
        ))}
      </header>
      <div className="max-h-[320px] min-h-[180px] overflow-auto">
        {tab === "operaciones" ? <Trades live={live} /> : null}
        {tab === "alertas" ? <Alerts alerts={alerts} /> : null}
        {tab === "metricas" ? <MetricsTable live={live} backtestIs={backtestIs} backtestOos={backtestOos} /> : null}
      </div>
    </section>
  );
}

function Trades({ live }: { live: Live | null }) {
  const closed = live?.operaciones_cerradas ?? [];
  if (closed.length === 0) return <Empty>Todavía no hay operaciones cerradas.</Empty>;
  return (
    <table className="w-full min-w-[640px] text-[12px]">
      <thead className="sticky top-0 bg-panel text-left text-[11px] text-ink-muted">
        <tr>
          {["Cierre (UTC)", "Par", "Lado", "Cantidad", "Entrada", "Salida", "Motivo"].map((h) => <th key={h} className="px-3 py-1.5 font-normal">{h}</th>)}
          <th className="px-3 text-right font-normal">P&L neto</th>
        </tr>
      </thead>
      <tbody className="num">
        {closed.map((p) => (
          <tr key={p.id} className="border-t border-line">
            <td className="px-3 py-1.5 text-ink-muted">{utc(p.cerrada)}</td>
            <td className="px-3 font-sans font-medium">{p.simbolo.split("/")[0]}</td>
            <td className={`px-3 font-sans text-[11px] uppercase ${p.lado === "long" ? "text-up" : "text-down"}`}>{p.lado}</td>
            <td className="px-3">{num(p.cantidad, 4)}</td>
            <td className="px-3">{price(p.entrada)}</td>
            <td className="px-3">{p.salida != null ? price(p.salida) : "—"}</td>
            <td className="px-3 font-sans text-ink-muted">{p.motivo_salida ?? "—"}</td>
            <td className={`px-3 text-right ${tone(p.pnl)}`}>{num(p.pnl, 2, true)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const LEVEL = {
  critical: { label: "CRÍTICA", className: "text-down" },
  warning: { label: "AVISO", className: "text-warn" },
  info: { label: "INFO", className: "text-ink-muted" },
} as const;

function Alerts({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) return <Empty>Sin alertas.</Empty>;
  return (
    <ul className="text-[12px]">
      {alerts.map((a, i) => (
        <li key={`${a.fecha}-${i}`} className="grid grid-cols-[8.5rem_4.5rem_1fr] gap-3 border-b border-line px-3 py-1.5">
          <span className="num text-ink-faint">{utc(a.fecha)}</span>
          <span className={`text-[11px] font-medium ${LEVEL[a.nivel].className}`}>{LEVEL[a.nivel].label}</span>
          <span className="min-w-0 break-words">{a.mensaje}</span>
        </li>
      ))}
    </ul>
  );
}

const ROWS: [keyof Metrics, string, (v: number | null | undefined) => string][] = [
  ["retorno_neto", "Retorno neto", (v) => pct(v)],
  ["max_drawdown", "Máximo drawdown", (v) => pct(v, 2, false)],
  ["sharpe", "Sharpe", (v) => num(v)],
  ["sortino", "Sortino", (v) => num(v)],
  ["operaciones", "Operaciones", (v) => num(v, 0)],
  ["tasa_acierto", "Tasa de acierto", (v) => pct(v, 1, false)],
  ["ganancia_promedio", "Ganancia promedio", (v) => num(v)],
  ["perdida_promedio", "Pérdida promedio", (v) => num(v)],
  ["profit_factor", "Profit factor", (v) => num(v)],
  ["r_promedio", "R promedio", (v) => num(v, 2, true)],
  ["comisiones", "Comisiones (USDT)", (v) => num(v)],
  ["funding", "Funding (USDT)", (v) => num(v)],
];

function MetricsTable({ live, backtestIs, backtestOos }: { live: Live | null; backtestIs: Backtest | null; backtestOos: Backtest | null }) {
  const columns: [string, Metrics | null | undefined][] = [
    ["Bot en vivo", live?.metricas_bot],
    ["BTC en vivo", live?.metricas_btc],
    ["Backtest IS", backtestIs?.metricas_bot],
    ["BTC IS", backtestIs?.metricas_btc],
    ["Backtest OOS", backtestOos?.metricas_bot],
    ["BTC OOS", backtestOos?.metricas_btc],
  ];
  return (
    <table className="w-full min-w-[720px] text-[12px]">
      <thead className="sticky top-0 bg-panel text-[11px] text-ink-muted">
        <tr>
          <th className="px-3 py-1.5 text-left font-normal">Métrica</th>
          {columns.map(([name]) => <th key={name} className="px-3 text-right font-normal">{name}</th>)}
        </tr>
      </thead>
      <tbody className="num">
        {ROWS.map(([key, label, format]) => (
          <tr key={key} className="border-t border-line">
            <td className="px-3 py-1.5 font-sans text-ink-muted">{label}</td>
            {columns.map(([name, m]) => {
              const value = m?.[key] as number | null | undefined;
              const colored = key === "retorno_neto" || key === "r_promedio";
              return <td key={name} className={`px-3 text-right ${colored ? tone(value) : ""}`}>{m ? format(value) : "—"}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
