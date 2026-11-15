"use client";

import { useEffect, useState } from "react";

import { type Candle, fetchCandles } from "@/lib/binance";
import { num, pct, price } from "@/lib/format";
import { closedOnly, reading, type Reading } from "@/lib/indicators";

import { useLiveMarket } from "./live-market";

const REFRESH_MS = 5 * 60_000; // las velas de 4h y 1d cambian despacio; el precio sí va en vivo

/** Velas cerradas de 4h (bot de rupturas) y diarias (bot de tendencia) de una moneda. */
function useCandles(coin: string): { h4: Candle[]; daily: Candle[] } | null {
  const [data, setData] = useState<{ coin: string; h4: Candle[]; daily: Candle[] } | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    const load = () => Promise.all([fetchCandles(coin, "4h", 1000, abort.signal), fetchCandles(coin, "1d", 200, abort.signal)])
      .then(([h4, daily]) => setData({ coin, h4: closedOnly(h4, 14_400), daily: closedOnly(daily, 86_400) }))
      .catch((err: unknown) => { if (!abort.signal.aborted) console.error(err); });
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => { abort.abort(); clearInterval(timer); };
  }, [coin]);
  return data && data.coin === coin ? data : null;
}

type Vote = -1 | 0 | 1;
const sign = (v: number | null | undefined): Vote => (v == null || v === 0 ? 0 : v > 0 ? 1 : -1);

function votes(r: Reading): { label: string; vote: Vote }[] {
  const channel = r.upper != null && r.price > r.upper ? 1 : r.lower != null && r.price < r.lower ? -1 : 0;
  return [
    { label: "EMA 50 vs 200 (4h)", vote: sign(r.emaFast != null && r.emaSlow != null ? r.emaFast - r.emaSlow : null) },
    { label: "Tendencia 20/60/120 días", vote: sign(r.trend?.signal) },
    { label: "Canal de 20 velas (4h)", vote: channel as Vote },
  ];
}

/** Lo que mira cada bot para esta moneda, y si la dirección elegida va a favor o en contra. */
export function MarketReading({ coin, side }: { coin: string; side: "long" | "short" }) {
  const candles = useCandles(coin);
  const live = useLiveMarket().tickers[coin]?.price;
  if (!candles || candles.h4.length < 30) return <p className="mt-2 text-[11px] text-ink-faint">Calculando indicadores de {coin}…</p>;
  const r = reading(candles.h4, candles.daily, live ?? candles.h4.at(-1)!.close);
  const want = side === "long" ? 1 : -1;
  const list = votes(r);
  const decided = list.filter((v) => v.vote !== 0);
  const favor = decided.filter((v) => v.vote === want).length;

  const trendLabel = r.emaFast == null || r.emaSlow == null ? "—" : r.emaFast > r.emaSlow ? "alcista" : "bajista";
  const rsiZone = r.rsi == null ? "" : r.rsi >= 70 ? "sobrecompra" : r.rsi <= 30 ? "sobreventa" : "neutral";
  const channelState = r.upper == null || r.lower == null ? "—"
    : r.price > r.upper ? `rompe arriba (+${pct(r.price / r.upper - 1, 1, false)})`
    : r.price < r.lower ? `rompe abajo (${pct(r.price / r.lower - 1, 1)})`
    : `dentro · a ${pct(r.upper / r.price - 1, 1, false)} del máx. y ${pct(1 - r.lower / r.price, 1, false)} del mín.`;

  return (
    <div className="mt-2 rounded-[3px] border border-line">
      <div className="flex items-baseline justify-between border-b border-line px-2 py-1">
        <span className="text-[11px] text-ink-muted">Lectura de {coin} · lo que mira el bot</span>
        <span className={`text-[11px] font-medium ${favor === decided.length && decided.length ? "text-up" : favor === 0 && decided.length ? "text-down" : "text-warn"}`}>
          {side} a favor de {favor} de {list.length}
        </span>
      </div>
      <dl className="num grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-2 py-1.5 text-[11px]">
        <dt className="font-sans text-ink-faint">Tendencia 4h</dt>
        <dd className="text-right">{trendLabel} <span className="text-ink-faint">EMA50 {r.emaFast ? price(r.emaFast) : "—"} · EMA200 {r.emaSlow ? price(r.emaSlow) : "—"}</span></dd>
        <dt className="font-sans text-ink-faint">RSI 14 (4h)</dt>
        <dd className={`text-right ${rsiZone === "sobrecompra" ? "text-down" : rsiZone === "sobreventa" ? "text-up" : ""}`}>{num(r.rsi, 1)} <span className="text-ink-faint">{rsiZone}</span></dd>
        <dt className="font-sans text-ink-faint">Canal 20 (4h)</dt>
        <dd className="text-right">{r.lower ? price(r.lower) : "—"} – {r.upper ? price(r.upper) : "—"} <span className="block text-ink-faint">{channelState}</span></dd>
        <dt className="font-sans text-ink-faint">Volatilidad</dt>
        <dd className="text-right">ATR {pct(r.atrPct, 2, false)} por vela de 4h</dd>
        <dt className="font-sans text-ink-faint">Señal tendencia</dt>
        <dd className="text-right">
          {r.trend ? <>{num(r.trend.signal, 2, true)} <span className="text-ink-faint">({[20, 60, 120].map((n) => `${n}d ${r.trend!.parts[n] > 0 ? "▲" : r.trend!.parts[n] < 0 ? "▼" : "■"}`).join(" · ")})</span></> : "—"}
        </dd>
      </dl>
      <ul className="flex flex-wrap gap-x-3 border-t border-line px-2 py-1 text-[11px]">
        {list.map((v) => (
          <li key={v.label} className={v.vote === 0 ? "text-ink-faint" : v.vote === want ? "text-up" : "text-down"}>
            {v.vote === 0 ? "■" : v.vote === want ? "✓" : "✗"} {v.label}
          </li>
        ))}
      </ul>
      <p className="border-t border-line px-2 py-1 text-[10px] leading-4 text-ink-faint">
        El canal cuenta solo si el precio ya está fuera. El bot de rupturas entra al cerrar una vela de 4h fuera del canal;
        no es una recomendación.
      </p>
    </div>
  );
}
