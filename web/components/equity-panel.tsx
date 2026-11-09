"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid, LabelList, Line, LineChart, Tooltip, XAxis, YAxis,
  type TooltipContentProps, type TooltipValueType,
} from "recharts";

import { num, pct, tone, utc } from "@/lib/format";
import type { Backtest, CurvePoint, Live, Metrics } from "@/lib/types";

import { Empty, Stat } from "./panel";

type View = "vivo" | "is" | "oos";
const SERIES = [
  { key: "bot", label: "Bot", color: "var(--series-bot)" },
  { key: "btc", label: "Comprar y mantener BTC", color: "var(--series-btc)" },
] as const;

export function EquityPanel({ live, backtestIs, backtestOos }: {
  live: Live | null;
  backtestIs: Backtest | null;
  backtestOos: Backtest | null;
}) {
  // Sin curva en vivo todavía, se abre en el backtest out-of-sample.
  const [view, setView] = useState<View>((live?.curva.length ?? 0) >= 2 ? "vivo" : "oos");
  const [showTable, setShowTable] = useState(false);

  const source = view === "vivo"
    ? { curve: live?.curva ?? [], bot: live?.metricas_bot, btc: live?.metricas_btc,
        note: `${num(live?.dias_en_papel, 1)} días en papel` }
    : (() => {
        const b = view === "is" ? backtestIs : backtestOos;
        return { curve: b?.curva ?? [], bot: b?.metricas_bot, btc: b?.metricas_btc,
          note: b ? `${utc(b.desde, true).slice(0, 10)} → ${utc(b.hasta, true).slice(0, 10)}${b.kill_switch ? ` · kill switch ${b.kill_switch.slice(0, 10)}` : ""}` : "" };
      })();

  return (
    <section className="flex min-w-0 flex-col bg-panel">
      <header className="flex h-8 shrink-0 items-center gap-3 border-b border-line px-3">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-muted">Capital</h2>
        <div role="tablist" className="flex h-full min-w-0 items-stretch overflow-x-auto">
          {([["vivo", "En vivo"], ["is", "Backtest IS"], ["oos", "Backtest OOS"]] as const).map(([key, label]) => (
            <button key={key} role="tab" aria-selected={view === key} onClick={() => setView(key)}
              className={`shrink-0 whitespace-nowrap border-b-2 px-2.5 text-[12px] transition-colors ${view === key ? "border-series-bot text-ink" : "border-transparent text-ink-muted hover:text-ink"}`}>
              {label}
            </button>
          ))}
        </div>
        <span className="num ml-auto hidden truncate text-[11px] text-ink-faint sm:block">{source.note}</span>
      </header>

      <MetricStrip bot={source.bot} btc={source.btc} />

      <div className="flex items-center gap-4 px-3 pt-2 text-[11px] text-ink-muted">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <button onClick={() => setShowTable((v) => !v)} className="ml-auto text-ink-faint underline-offset-2 hover:text-ink hover:underline">
          {showTable ? "Ver gráfico" : "Ver tabla"}
        </button>
      </div>

      <div className="h-[340px] px-1 pb-2">
        {source.curve.length < 2 ? (
          <Empty>
            {view === "vivo"
              ? "La curva aparece cuando el bot acumule ciclos: registra el capital una vez por hora."
              : "Sin datos de backtest publicados."}
          </Empty>
        ) : showTable ? (
          <CurveTable curve={source.curve} />
        ) : (
          <Chart curve={source.curve} />
        )}
      </div>
    </section>
  );
}

function MetricStrip({ bot, btc }: { bot?: Metrics | null; btc?: Metrics | null }) {
  const diff = bot?.retorno_neto != null && btc?.retorno_neto != null ? bot.retorno_neto - btc.retorno_neto : null;
  return (
    <div className="grid grid-cols-3 border-b border-line sm:grid-cols-6 [&>*]:border-line [&>*:not(:last-child)]:border-r">
      <Stat label="Retorno del bot" value={pct(bot?.retorno_neto)} valueClass={tone(bot?.retorno_neto)} />
      <Stat label="Comprar BTC" value={pct(btc?.retorno_neto)} valueClass={tone(btc?.retorno_neto)} />
      <Stat label="Diferencia" value={pct(diff)} valueClass={tone(diff)} sub="bot − BTC" />
      <Stat label="Máx. drawdown" value={pct(bot?.max_drawdown, 2, false)} sub={`BTC ${pct(btc?.max_drawdown, 1, false)}`} />
      <Stat label="Sharpe" value={num(bot?.sharpe)} sub={`BTC ${num(btc?.sharpe)}`} />
      <Stat label="Operaciones" value={bot?.operaciones ?? "—"}
        sub={bot?.profit_factor != null ? `PF ${num(bot.profit_factor)}` : undefined} />
    </div>
  );
}

function Chart({ curve }: { curve: CurvePoint[] }) {
  const spanDays = (new Date(curve.at(-1)!.t).getTime() - new Date(curve[0].t).getTime()) / 86_400_000;
  const tickFormat = (t: string) => (spanDays > 60 ? t.slice(0, 7) : spanDays > 2 ? t.slice(5, 10) : utc(t, false));
  const last = curve.length - 1;
  const compact = useNarrow();

  return (
    // `responsive` sigue el tamaño del contenedor con reglas CSS normales (ancho 100%, alto del panel).
    <LineChart responsive style={{ width: "100%", height: "100%" }} data={curve}
      margin={{ top: 12, right: compact ? 44 : 64, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis dataKey="t" tickFormatter={tickFormat} minTickGap={compact ? 32 : 48} tickLine={false}
          axisLine={{ stroke: "var(--line-strong)" }} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
        <YAxis domain={["auto", "auto"]} width={compact ? 44 : 56} tickLine={false} axisLine={false}
          tickFormatter={(v: number) => num(v, 0)} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
        <Tooltip content={TooltipBox} cursor={{ stroke: "var(--ink-faint)", strokeDasharray: "3 3" }} isAnimationActive={false} />
        {SERIES.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.label} type="monotone" stroke={s.color} strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2 }} isAnimationActive={false}>
            {/* Etiqueta directa al final de cada línea. */}
            <LabelList dataKey={s.key} content={({ x, y, value, index }) =>
              index === last ? (
                <text x={Number(x) + 6} y={Number(y)} dy={4} fill={s.color} fontSize={11} className="num">
                  {num(Number(value), 0)}
                </text>
              ) : null} />
          </Line>
        ))}
    </LineChart>
  );
}

/** Pantallas angostas: ejes y margen más compactos para dejarle ancho a la curva. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

function TooltipBox({ active, payload, label }: TooltipContentProps<TooltipValueType, string | number>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[3px] border border-line-strong bg-panel-raised px-2.5 py-2 text-[12px]">
      <div className="num mb-1 text-ink-muted">{utc(String(label))} UTC</div>
      {SERIES.map((s) => {
        const item = payload.find((p) => p.dataKey === s.key);
        return (
          <div key={s.key} className="flex items-center gap-2">
            <span className="h-0.5 w-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-ink-muted">{s.label}</span>
            <span className="num ml-auto pl-4">{num(Number(item?.value), 2)}</span>
          </div>
        );
      })}
    </div>
  );
}

function CurveTable({ curve }: { curve: CurvePoint[] }) {
  const rows = [...curve].reverse();
  return (
    <div className="h-full overflow-auto px-2">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-panel text-left text-[11px] text-ink-muted">
          <tr><th className="py-1.5 font-normal">Fecha (UTC)</th><th className="text-right font-normal">Bot</th><th className="text-right font-normal">BTC</th></tr>
        </thead>
        <tbody className="num">
          {rows.map((p) => (
            <tr key={p.t} className="border-t border-line">
              <td className="py-1 text-ink-muted">{utc(p.t)}</td>
              <td className="text-right">{num(p.bot)}</td>
              <td className="text-right">{num(p.btc)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
