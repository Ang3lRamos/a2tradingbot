import { pct, utc } from "@/lib/format";
import type { BotState } from "@/lib/types";

import { Heartbeat } from "./heartbeat";
import { LiveBadge } from "./live-market";

const MODES = {
  operar: { label: "Operando", dot: "bg-up", text: "text-up" },
  solo_cierre: { label: "Solo cierre", dot: "bg-warn", text: "text-warn" },
  kill_switch: { label: "Kill switch", dot: "bg-down", text: "text-down" },
} as const;

export function StatusBar({ state, updated }: { state: BotState | null; updated: string | null }) {
  const mode = state?.modo ? MODES[state.modo] : null;

  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line bg-panel px-3 py-2">
      <div className="flex items-baseline gap-2">
        <span className="text-[15px] font-semibold tracking-tight">tradebot</span>
        <span className="num text-[11px] text-ink-faint">{state?.variante ?? "—"}</span>
      </div>

      <Item label="Estado">
        <Heartbeat lastCycle={state?.ultimo_ciclo} />
      </Item>

      <Item label="Modo">
        {mode ? (
          <span className={`flex items-center gap-1.5 ${mode.text}`}>
            <span className={`size-1.5 rounded-[1px] ${mode.dot}`} />
            {mode.label}
            {state?.motivo && state.modo !== "operar" ? <span className="text-ink-faint">({state.motivo})</span> : null}
          </span>
        ) : (
          "—"
        )}
      </Item>

      <Item label="Claude hoy">
        <span className="num">
          {state?.llamadas_ia_hoy ?? 0}
          <span className="text-ink-faint">/{state?.limite_ia_diario ?? "—"}</span>
        </span>
      </Item>

      <Item label="Riesgo">
        <span className="num">
          {pct(state?.riesgo_por_operacion, 1, false)}
          <span className="text-ink-faint"> · kill {pct(state?.kill_switch_pct, 0, false)}</span>
        </span>
      </Item>

      <div className="flex items-center gap-2 text-[11px] text-ink-faint sm:ml-auto">
        <LiveBadge />
        <span className="rounded-[2px] border border-line-strong px-1.5 py-px uppercase tracking-wider">Papel</span>
        <span className="num" title="Los datos del bot se vuelven a pedir cada minuto">bot {utc(updated)} UTC</span>
      </div>
    </header>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-faint">{label}</span>
      {children}
    </div>
  );
}
