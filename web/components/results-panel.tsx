"use client";

import { num, pct, tone } from "@/lib/format";
import type { Live, Position } from "@/lib/types";

import { Empty } from "./panel";
import { rMultiple } from "./pnl-summary";

type Summary = {
  n: number; wins: number; losses: number; won: number; lost: number; net: number; fees: number;
  best: number | null; worst: number | null; avgWin: number | null; avgLoss: number | null;
  profitFactor: number | null; avgR: number | null; streak: { kind: "win" | "loss"; n: number } | null;
};

export function summarize(trades: Position[]): Summary {
  const pnls = trades.map((p) => p.pnl ?? 0);
  const wins = pnls.filter((v) => v > 0);
  const losses = pnls.filter((v) => v <= 0);
  const won = wins.reduce((a, b) => a + b, 0);
  const lost = losses.reduce((a, b) => a + b, 0);
  const rs = trades.map(rMultiple).filter((r): r is number => r != null);
  // Racha actual: operaciones más recientes con el mismo resultado (la lista viene de la más nueva a la más vieja).
  const byClose = [...trades].sort((a, b) => (b.cerrada ?? "").localeCompare(a.cerrada ?? ""));
  let streak: Summary["streak"] = null;
  for (const p of byClose) {
    const kind = (p.pnl ?? 0) > 0 ? "win" : "loss";
    if (!streak) streak = { kind, n: 1 };
    else if (streak.kind === kind) streak.n += 1;
    else break;
  }
  return {
    n: trades.length, wins: wins.length, losses: losses.length, won, lost, net: won + lost,
    fees: trades.reduce((a, p) => a + (p.comisiones ?? 0), 0),
    best: pnls.length ? Math.max(...pnls) : null, worst: pnls.length ? Math.min(...pnls) : null,
    avgWin: wins.length ? won / wins.length : null, avgLoss: losses.length ? lost / losses.length : null,
    profitFactor: lost < 0 ? won / -lost : null, avgR: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null,
    streak,
  };
}

/** Ganadas y perdidas: cuánto entró y cuánto salió, la estrategia separada de lo manual. */
export function ResultsPanel({ live }: { live: Live | null }) {
  const closed = live?.operaciones_cerradas ?? [];
  if (closed.length === 0) return <Empty>Todavía no hay operaciones cerradas.</Empty>;
  const groups: [string, Summary][] = [["Estrategia", summarize(closed.filter((p) => p.origen !== "manual"))]];
  const manual = closed.filter((p) => p.origen === "manual");
  if (manual.length) groups.push(["Manual", summarize(manual)], ["Total", summarize(closed)]);
  const all = groups.at(-1)![1];

  return (
    <div>
      <Totals s={all} />
      <table className="w-full min-w-[520px] text-[12px]">
        <thead className="text-[11px] text-ink-muted">
          <tr>
            <th className="px-3 py-1.5 text-left font-normal" />
            {groups.map(([name]) => <th key={name} className="px-3 text-right font-normal">{name}</th>)}
          </tr>
        </thead>
        <tbody className="num">
          {ROWS.map(([label, value, colored]) => (
            <tr key={label} className="border-t border-line">
              <td className="px-3 py-1.5 font-sans text-ink-muted">{label}</td>
              {groups.map(([name, s]) => {
                const v = value(s);
                return <td key={name} className={`px-3 text-right ${colored && typeof v.raw === "number" ? tone(v.raw) : ""}`}>{v.text}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line px-3 py-2 text-[11px] leading-4 text-ink-faint">
        P&L neto de comisiones. Las operaciones manuales se muestran aparte y no entran en las métricas de la estrategia.
        El bot de tendencia no cierra operaciones: su resultado está en el capital.
      </p>
    </div>
  );
}

type Cell = { text: string; raw?: number | null };
const ROWS: [string, (s: Summary) => Cell, boolean][] = [
  ["Operaciones", (s) => ({ text: `${s.n}` }), false],
  ["Ganadas / perdidas", (s) => ({ text: `${s.wins} / ${s.losses}` }), false],
  ["Acierto", (s) => ({ text: pct(s.n ? s.wins / s.n : null, 0, false) }), false],
  ["Total ganado", (s) => ({ text: num(s.won, 2, true), raw: s.won }), true],
  ["Total perdido", (s) => ({ text: num(s.lost, 2, true), raw: s.lost }), true],
  ["Neto", (s) => ({ text: num(s.net, 2, true), raw: s.net }), true],
  ["Ganancia promedio", (s) => ({ text: num(s.avgWin, 2, true), raw: s.avgWin }), true],
  ["Pérdida promedio", (s) => ({ text: num(s.avgLoss, 2, true), raw: s.avgLoss }), true],
  ["Mayor ganancia", (s) => ({ text: num(s.best, 2, true), raw: s.best }), true],
  ["Mayor pérdida", (s) => ({ text: num(s.worst, 2, true), raw: s.worst }), true],
  ["Profit factor", (s) => ({ text: num(s.profitFactor) }), false],
  ["R promedio", (s) => ({ text: num(s.avgR, 2, true), raw: s.avgR }), true],
  ["Racha actual", (s) => ({ text: s.streak ? `${s.streak.n} ${s.streak.kind === "win" ? "ganada" : "perdida"}${s.streak.n > 1 ? "s" : ""}` : "—" }), false],
  ["Comisiones", (s) => ({ text: num(s.fees) }), false],
];

/** Barra de lo ganado contra lo perdido, en la misma escala. */
function Totals({ s }: { s: Summary }) {
  const scale = Math.max(s.won, -s.lost, 1e-9);
  return (
    <div className="grid grid-cols-3 border-b border-line [&>*:not(:last-child)]:border-r [&>*]:border-line">
      <Figure label="Total ganado" value={num(s.won, 2, true)} className="text-up" sub={`${s.wins} ganadas`}
        bar={<span className="block h-1 rounded-full bg-up" style={{ width: `${(s.won / scale) * 100}%` }} />} />
      <Figure label="Total perdido" value={num(s.lost, 2, true)} className="text-down" sub={`${s.losses} perdidas`}
        bar={<span className="block h-1 rounded-full bg-down" style={{ width: `${(-s.lost / scale) * 100}%` }} />} />
      <Figure label="Neto" value={num(s.net, 2, true)} className={tone(s.net)} sub="USDT, tras comisiones" />
    </div>
  );
}

function Figure({ label, value, sub, className, bar }: { label: string; value: string; sub: string; className: string; bar?: React.ReactNode }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="text-[11px] text-ink-muted">{label}</div>
      <div className={`num text-[17px] font-medium leading-6 ${className}`}>{value}</div>
      <div className="mt-1 h-1 w-full rounded-full bg-line">{bar}</div>
      <div className="num mt-1 text-[11px] text-ink-faint">{sub}</div>
    </div>
  );
}
