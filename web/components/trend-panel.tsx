import { num, pct, tone, utc } from "@/lib/format";
import type { Trend } from "@/lib/types";

import { Empty, Panel, Stat } from "./panel";
import { LiveEquity } from "./positions-panel";

/** Bot de tendencia largo/corto: capital, exposición por moneda y último rebalanceo. */
export function TrendPanel({ trend }: { trend: Trend | null | undefined }) {
  if (!trend) {
    return (
      <Panel title="Tendencia L/S" aside="cuenta virtual">
        <Empty>Sin datos todavía: el bot de tendencia rebalancea cada día a las 00:15 UTC.</Empty>
      </Panel>
    );
  }
  const change = trend.capital_actual / trend.capital_inicial - 1;
  const gross = trend.pesos.reduce((sum, w) => sum + Math.abs(w.peso), 0);
  // Escala común para que las barras se comparen entre sí; nunca menor a 50% para no exagerar pesos chicos.
  const scale = Math.max(0.5, ...trend.pesos.map((w) => Math.abs(w.peso)));
  const lastDay = trend.operaciones[0]?.fecha;
  const lastTrades = trend.operaciones.filter((t) => t.fecha === lastDay);

  return (
    <Panel title="Tendencia L/S" aside="cuenta virtual">
      <div className="grid grid-cols-2 border-b border-line [&>*:first-child]:border-r [&>*:first-child]:border-line">
        <Stat label="Capital ahora" value={<LiveEquity source="tendencia" trend={trend} />} sub={`inicial ${num(trend.capital_inicial, 0)} USDT`} />
        <Stat label="Retorno" value={pct(change)} valueClass={tone(change)} sub={`exposición ${pct(gross, 0, false)}`} />
      </div>

      <ul className="px-3 py-2">
        {trend.pesos.map((w) => {
          const long = w.peso >= 0;
          const width = `${(Math.abs(w.peso) / scale) * 50}%`;
          return (
            <li key={w.simbolo} className="grid grid-cols-[34px_minmax(0,1fr)_92px] items-center gap-2 py-1 text-[12px]">
              <span className="font-medium">{w.simbolo.split("/")[0]}</span>
              <span className="relative h-2 rounded-sm bg-panel-raised" aria-hidden>
                <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                <span className={`absolute inset-y-0 rounded-sm ${long ? "left-1/2 bg-up" : "right-1/2 bg-down"}`} style={{ width }} />
              </span>
              <span className="num text-right">
                <span className={long ? "text-up" : "text-down"}>{long ? "▲" : "▼"}</span> {pct(w.peso, 1)}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="border-t border-line px-3 py-2 text-[11px] leading-4 text-ink-faint">
        {lastDay
          ? <>Último rebalanceo {utc(lastDay)} UTC: {lastTrades.map((t) => `${t.simbolo.split("/")[0]} ${pct(t.peso_antes, 0)} → ${pct(t.peso_despues, 0)}`).join(", ")}.</>
          : "Todavía sin rebalanceos."}{" "}
        Precios reales de Binance, con comisión, slippage y funding; sin órdenes en el exchange.
      </p>
    </Panel>
  );
}
