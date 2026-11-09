import { num, pct, price, tone, utc } from "@/lib/format";
import type { Ai, BotState, Live } from "@/lib/types";

import { Empty, Panel, Stat } from "./panel";

export function AccountPanel({ live, state }: { live: Live | null; state: BotState | null }) {
  return (
    <Panel title="Cuenta" aside="Binance Demo">
      <div className="grid grid-cols-2 [&>*]:border-line [&>*:nth-child(odd)]:border-r [&>*:nth-child(-n+2)]:border-b">
        <Stat label="Capital" value={num(live?.capital_actual)} sub="USDT" />
        <Stat label="Días en papel" value={num(live?.dias_en_papel, 1)} sub="meta: 30" />
        <Stat label="Abiertas" value={live?.posiciones_abiertas.length ?? 0} sub={`máx. 3`} />
        <Stat label="Cerradas" value={live?.operaciones_cerradas.length ?? 0} sub="meta: 100+" />
      </div>
      <p className="border-t border-line px-3 py-2 text-[11px] leading-4 text-ink-faint">
        Último ciclo {utc(state?.ultimo_ciclo)} UTC. Con menos de 30 operaciones los resultados todavía no permiten concluir nada.
      </p>
    </Panel>
  );
}

export function PositionsPanel({ live }: { live: Live | null }) {
  const open = live?.posiciones_abiertas ?? [];
  return (
    <Panel title="Posiciones" aside={`${open.length} abiertas`}>
      {open.length === 0 ? (
        <Empty>Sin posiciones abiertas.</Empty>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="text-left text-[11px] text-ink-muted">
            <tr><th className="px-3 py-1.5 font-normal">Par</th><th className="font-normal">Cant.</th><th className="font-normal">Entrada</th><th className="pr-3 text-right font-normal">Stop</th></tr>
          </thead>
          <tbody className="num">
            {open.map((p) => (
              <tr key={p.id} className="border-t border-line">
                <td className="px-3 py-1.5">
                  <span className="font-sans font-medium">{p.simbolo.split("/")[0]}</span>{" "}
                  <span className={`font-sans text-[11px] uppercase ${p.lado === "long" ? "text-up" : "text-down"}`}>{p.lado === "long" ? "▲ long" : "▼ short"}</span>
                </td>
                <td>{num(p.cantidad, 4)}</td>
                <td>{price(p.entrada)}</td>
                <td className="pr-3 text-right">{price(p.stop)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

const VERDICT = {
  mejor: { label: "Elige mejor que el azar", className: "text-up", mark: "▲" },
  peor: { label: "Elige peor que el azar", className: "text-down", mark: "▼" },
  indistinguible: { label: "No se distingue del azar", className: "text-ink-muted", mark: "■" },
} as const;

export function AiPanel({ ai }: { ai: Ai | null }) {
  const ev = ai?.evaluacion;
  return (
    <Panel title="Analista IA" aside={ev ? `${ev.revisadas}/${ai?.muestra} revisadas` : undefined}>
      {!ev ? (
        <Empty>Sin revisiones todavía.</Empty>
      ) : (
        <div>
          <div className={`flex items-center gap-1.5 border-b border-line px-3 py-2 font-medium ${VERDICT[ev.veredicto].className}`}>
            <span aria-hidden>{VERDICT[ev.veredicto].mark}</span>
            {VERDICT[ev.veredicto].label}
          </div>
          <div className="grid grid-cols-2 border-b border-line [&>*:first-child]:border-r [&>*]:border-line">
            <Stat label="Habilidad de selección" value={`${num(ev.habilidad, 3, true)} R`} valueClass={tone(ev.habilidad)}
              sub={`IC 90%: ${num(ev.intervalo[0], 2, true)} a ${num(ev.intervalo[1], 2, true)}`} />
            <Stat label="R por unidad de riesgo" value={num(ev.r_con_ia, 3, true)} valueClass={tone(ev.r_con_ia)}
              sub={`sin IA ${num(ev.r_sin_ia, 3, true)}`} />
          </div>
          <table className="w-full text-[12px]">
            <thead className="text-left text-[11px] text-ink-muted">
              <tr><th className="px-3 py-1.5 font-normal">Decisión</th><th className="text-right font-normal">n</th><th className="text-right font-normal">R medio</th><th className="pr-3 text-right font-normal">Tamaño</th></tr>
            </thead>
            <tbody className="num">
              {ev.por_decision.map((d) => (
                <tr key={d.decision} className="border-t border-line">
                  <td className="px-3 py-1.5 font-sans">{d.decision}</td>
                  <td className="text-right">{d.senales}</td>
                  <td className={`text-right ${tone(d.r_medio)}`}>{num(d.r_medio, 2, true)}</td>
                  <td className="pr-3 text-right">{num(d.tamano_medio, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line px-3 py-2 text-[11px] leading-4 text-ink-faint">
            Reducir el tamaño de todas las señales no cuenta como habilidad: se compara contra un recorte uniforme. {pct(ev.tamano_medio, 0, false)} de tamaño medio; ~{num(ev.tokens_entrada, 0)} tokens por revisión.
          </p>
        </div>
      )}
    </Panel>
  );
}
