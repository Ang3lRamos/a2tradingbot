"use client";

import { pct, price, tone } from "@/lib/format";
import type { Market } from "@/lib/types";

import { useLiveMarket } from "./live-market";
import { Empty, Panel } from "./panel";

export function Markets({ markets }: { markets: Market[] }) {
  const { tickers, selected, select } = useLiveMarket();
  return (
    <Panel title="Mercados" aside="perpetuos · en vivo">
      {markets.length === 0 ? (
        <Empty>Sin datos de mercado.</Empty>
      ) : (
        <ul>
          {markets.map((m) => {
            const t = tickers[m.simbolo];
            const last = t?.price ?? m.precio;
            const change = t?.change24h ?? m.cambio_24h;
            // La serie publicada termina en la última vela cerrada; se le agrega el precio de ahora.
            const series = t ? [...m.serie_24h, t.price] : m.serie_24h;
            return (
              <li key={m.simbolo} className="border-b border-line last:border-b-0">
                <button onClick={() => select(m.simbolo)} aria-pressed={selected === m.simbolo}
                  className={`grid w-full grid-cols-[3rem_1fr_5rem] items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-panel-raised ${selected === m.simbolo ? "bg-panel-raised" : ""}`}>
                  <div>
                    <div className="font-medium">{m.simbolo}</div>
                    <div className="text-[11px] text-ink-faint">USDT</div>
                  </div>
                  <Sparkline values={series} up={(change ?? 0) >= 0} />
                  <div className="text-right">
                    <LivePrice value={last} />
                    <div className={`num text-[11px] ${tone(change)}`}>{pct(change)}</div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

/** El precio parpadea en verde o rojo cuando cambia; `key` reinicia la animación. */
function LivePrice({ value }: { value: number }) {
  return <div key={value} className="num tick">{price(value)}</div>;
}

/** Mini gráfico de las últimas 24 velas más el precio en vivo. Decorativo: el número a la derecha es el dato. */
function Sparkline({ values, up }: { values: number[]; up: boolean }) {
  if (values.length < 2) return <div />;
  const w = 100;
  const h = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-7 w-full" aria-hidden>
      <polyline points={points} fill="none" strokeWidth="1.5" vectorEffect="non-scaling-stroke"
        className={up ? "stroke-up" : "stroke-down"} />
    </svg>
  );
}
