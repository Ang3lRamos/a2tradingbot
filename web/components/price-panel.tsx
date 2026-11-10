"use client";

import { useState } from "react";

import { base, type Interval } from "@/lib/binance";
import { pct, price, tone } from "@/lib/format";
import type { Live, Trend } from "@/lib/types";

import { CandleChart, type ChartLine, type ChartMarker } from "./candle-chart";
import { useLiveMarket } from "./live-market";

const INTERVALS: Interval[] = ["15m", "1h", "4h", "1d"];

/** Gráfico de velas en vivo de la moneda elegida, con las posiciones y operaciones de los dos bots encima. */
export function PricePanel({ symbols, live, trend }: { symbols: string[]; live: Live | null; trend: Trend | null }) {
  const { tickers, selected, select } = useLiveMarket();
  const [interval, setTimeframe] = useState<Interval>("4h");
  const ticker = tickers[selected];

  const open = (live?.posiciones_abiertas ?? []).filter((p) => base(p.simbolo) === selected);
  const lines: ChartLine[] = open.flatMap((p) => [
    { price: p.entrada, label: `Entrada ${p.lado}`, tone: "bot" as const },
    { price: p.stop, label: "Stop", tone: "down" as const, dashed: true },
  ]);
  const markers: ChartMarker[] = [
    ...(live?.posiciones_abiertas ?? []).concat(live?.operaciones_cerradas ?? [])
      .filter((p) => base(p.simbolo) === selected)
      .flatMap((p): ChartMarker[] => [
        { at: p.abierta, side: p.lado, kind: "entry", text: p.lado === "long" ? "L" : "S" },
        ...(p.cerrada ? [{ at: p.cerrada, side: p.lado, kind: "exit" as const, text: "×" }] : []),
      ]),
    ...(trend?.operaciones ?? [])
      .filter((t) => base(t.simbolo) === selected && interval !== "15m")
      .map((t): ChartMarker => ({ at: t.fecha, side: t.cantidad >= 0 ? "long" : "short", kind: "entry", text: "T" })),
  ];

  return (
    <section className="flex min-w-0 flex-col bg-panel">
      <header className="flex h-8 shrink-0 items-center gap-3 border-b border-line px-3">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-muted">Precio</h2>
        <div role="tablist" className="flex h-full items-stretch">
          {symbols.map((s) => (
            <button key={s} role="tab" aria-selected={selected === s} onClick={() => select(s)}
              className={`border-b-2 px-2.5 text-[12px] font-medium transition-colors ${selected === s ? "border-series-bot text-ink" : "border-transparent text-ink-muted hover:text-ink"}`}>
              {s}
            </button>
          ))}
        </div>
        <span className="num hidden text-[13px] sm:inline">{ticker ? price(ticker.price) : "—"}</span>
        <span className={`num hidden text-[11px] sm:inline ${tone(ticker?.change24h)}`}>{ticker ? `${pct(ticker.change24h)} 24h` : ""}</span>
        <div role="tablist" className="ml-auto flex h-full items-stretch">
          {INTERVALS.map((i) => (
            <button key={i} role="tab" aria-selected={interval === i} onClick={() => setTimeframe(i)}
              className={`num border-b-2 px-2 text-[11px] transition-colors ${interval === i ? "border-series-bot text-ink" : "border-transparent text-ink-faint hover:text-ink"}`}>
              {i}
            </button>
          ))}
        </div>
      </header>
      <div className="h-[360px]">
        <CandleChart symbol={selected} interval={interval} lines={lines} markers={markers} />
      </div>
      <p className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line px-3 py-1.5 text-[11px] text-ink-faint">
        <span><span className="text-up">▲</span>/<span className="text-down">▼</span> L, S: entradas de rupturas · ● salida</span>
        <span>T: rebalanceos de tendencia</span>
        <span>Línea azul: entrada · roja punteada: stop</span>
        <span className="ml-auto">Binance perpetuos · UTC</span>
      </p>
    </section>
  );
}
