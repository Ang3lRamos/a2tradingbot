import { pct, price, tone } from "@/lib/format";
import type { Market } from "@/lib/types";

import { Empty, Panel } from "./panel";

export function Markets({ markets }: { markets: Market[] }) {
  return (
    <Panel title="Mercados" aside="perpetuos · 1h">
      {markets.length === 0 ? (
        <Empty>Sin datos de mercado.</Empty>
      ) : (
        <ul>
          {markets.map((m) => (
            <li key={m.simbolo} className="grid grid-cols-[3rem_1fr_4.5rem] items-center gap-2 border-b border-line px-3 py-2 last:border-b-0">
              <div>
                <div className="font-medium">{m.simbolo}</div>
                <div className="text-[11px] text-ink-faint">USDT</div>
              </div>
              <Sparkline values={m.serie_24h} up={(m.cambio_24h ?? 0) >= 0} />
              <div className="text-right">
                <div className="num">{price(m.precio)}</div>
                <div className={`num text-[11px] ${tone(m.cambio_24h)}`}>{pct(m.cambio_24h)}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** Mini gráfico de las últimas 24 velas. Decorativo: el número a la derecha es el dato. */
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
