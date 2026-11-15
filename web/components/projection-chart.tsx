"use client";

import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, Tooltip, XAxis, YAxis,
  type TooltipContentProps, type TooltipValueType,
} from "recharts";

import { num, pct, utc } from "@/lib/format";
import type { CurvePoint, Projection } from "@/lib/types";

// Azul = el bot, como en el resto del dashboard; la expectativa del backtest va en gris neutro.
const BAND = "var(--ink-muted)";
const MEDIAN = "var(--ink-muted)";
const REAL = "var(--series-bot)";

export const PROJECTION_LEGEND = [
  { label: "Real", color: REAL, kind: "line" },
  { label: "Mediana del backtest", color: MEDIAN, kind: "dash" },
  { label: "Rango 10–90%", color: BAND, kind: "band" },
] as const;

type Row = { t: number; real?: number; p50?: number; band?: [number, number] };

/** Une la banda diaria y la curva real (horaria) en una sola serie con el tiempo como número. */
function merge(curve: CurvePoint[], projection: Projection): Row[] {
  const rows: Row[] = projection.puntos.map((p) => ({ t: Date.parse(p.t), p50: p.p50, band: [p.p10, p.p90] }));
  for (const point of curve) rows.push({ t: Date.parse(point.t), real: point.bot });
  return rows.sort((a, b) => a.t - b.t);
}

/** Banda vigente en un instante: interpolación lineal entre los dos días que lo rodean. */
export function bandAt(projection: Projection, t: number): { p10: number; p50: number; p90: number } | null {
  const points = projection.puntos;
  const i = points.findIndex((p) => Date.parse(p.t) >= t);
  if (i <= 0) return i === 0 ? points[0] : null;
  const [a, b] = [points[i - 1], points[i]];
  const w = (t - Date.parse(a.t)) / (Date.parse(b.t) - Date.parse(a.t));
  const mix = (x: number, y: number) => x + (y - x) * w;
  return { p10: mix(a.p10, b.p10), p50: mix(a.p50, b.p50), p90: mix(a.p90, b.p90) };
}

export function ProjectionVerdict({ curve, projection }: { curve: CurvePoint[]; projection: Projection }) {
  const last = curve.at(-1);
  const band = last ? bandAt(projection, Date.parse(last.t)) : null;
  if (!last || !band) return null;
  const where = last.bot > band.p90 ? { text: "por encima del rango esperado", className: "text-up" }
    : last.bot < band.p10 ? { text: "por debajo del rango esperado", className: "text-down" }
    : { text: "dentro del rango esperado", className: "text-ink" };
  return (
    <p className="px-3 pt-1 text-[11px] text-ink-muted">
      Hoy: <span className={`font-medium ${where.className}`}>{where.text}</span>
      <span className="num text-ink-faint"> · real {num(last.bot, 0)} vs mediana {num(band.p50, 0)} ({pct(last.bot / band.p50 - 1, 1)}) ·
        rango {num(band.p10, 0)}–{num(band.p90, 0)}</span>
    </p>
  );
}

export function ProjectionChart({ curve, projection, compact }: { curve: CurvePoint[]; projection: Projection; compact: boolean }) {
  const data = merge(curve, projection);
  const now = curve.length ? Date.parse(curve.at(-1)!.t) : null;
  return (
    <ComposedChart responsive style={{ width: "100%", height: "100%" }} data={data}
      margin={{ top: 12, right: compact ? 12 : 20, bottom: 0, left: 0 }}>
      <CartesianGrid vertical={false} stroke="var(--line)" />
      <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} minTickGap={compact ? 32 : 48}
        tickFormatter={(t: number) => new Date(t).toISOString().slice(5, 10)} tickLine={false}
        axisLine={{ stroke: "var(--line-strong)" }} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
      <YAxis domain={["auto", "auto"]} width={compact ? 44 : 56} tickLine={false} axisLine={false}
        tickFormatter={(v: number) => num(v, 0)} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
      <Tooltip content={TooltipBox} cursor={{ stroke: "var(--ink-faint)", strokeDasharray: "3 3" }} isAnimationActive={false} />
      <ReferenceLine y={projection.capital_inicial} stroke="var(--line-strong)" />
      {now ? <ReferenceLine x={now} stroke="var(--ink-faint)" strokeDasharray="2 4" label={{ value: "hoy", fill: "var(--ink-faint)", fontSize: 10, position: "insideTopRight" }} /> : null}
      <Area dataKey="band" stroke="none" fill={BAND} fillOpacity={0.16} connectNulls isAnimationActive={false} activeDot={false} />
      <Line dataKey="p50" stroke={MEDIAN} strokeWidth={1.5} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} activeDot={false} />
      <Line dataKey="real" stroke={REAL} strokeWidth={2} dot={false} connectNulls isAnimationActive={false}
        activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2 }} />
    </ComposedChart>
  );
}

function TooltipBox({ active, payload, label }: TooltipContentProps<TooltipValueType, string | number>) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as Row;
  return (
    <div className="rounded-[3px] border border-line-strong bg-panel-raised px-2.5 py-2 text-[12px]">
      <div className="num mb-1 text-ink-muted">{utc(new Date(Number(label)).toISOString())} UTC</div>
      {row.real != null ? <Line2 color={REAL} label="Real" value={num(row.real, 2)} /> : null}
      {row.p50 != null ? <Line2 color={MEDIAN} label="Mediana" value={num(row.p50, 2)} /> : null}
      {row.band ? <Line2 color={BAND} label="Rango 10–90%" value={`${num(row.band[0], 0)}–${num(row.band[1], 0)}`} /> : null}
    </div>
  );
}

function Line2({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-0.5 w-2.5 rounded-full" style={{ background: color }} />
      <span className="text-ink-muted">{label}</span>
      <span className="num ml-auto pl-4">{value}</span>
    </div>
  );
}
