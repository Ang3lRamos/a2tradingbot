"use client";

import { useRouter } from "next/navigation";
import { useActionState, useCallback, useEffect, useRef, useState } from "react";

import { getControlState, login, logout, refreshDashboard } from "@/app/actions";
import { utc } from "@/lib/format";
import type { BotState, Command, ControlState, Live, Market } from "@/lib/types";

import { AggressivenessForm, ManualTradeForm, OpenManualList } from "./control-forms";
import { Empty, Panel } from "./panel";

const POLL_MS = 4000;
const busy = (c: Command) => c.status === "pendiente" || c.status === "ejecutando";

/** Panel de control: agresividad de cada bot y operaciones manuales, detrás de una contraseña. */
export function ControlPanel({ state, live, markets }: { state: BotState | null; live: Live | null; markets: Market[] }) {
  const router = useRouter();
  const [control, setControl] = useState<ControlState | null>(null);
  const waiting = useRef(false);

  const reload = useCallback(async () => {
    const next = await getControlState();
    const finished = waiting.current && next.authed && !next.commands.some(busy);
    waiting.current = next.authed && next.commands.some(busy);
    setControl(next);
    if (finished) {
      // El bot ya ejecutó y republicó: se descarta la caché y se vuelve a pedir la página.
      await refreshDashboard();
      router.refresh();
    }
  }, [router]);

  // Estado inicial: si hay sesión abierta y órdenes recientes. El estado se fija en el callback de la promesa.
  useEffect(() => {
    let active = true;
    getControlState().then((next) => {
      if (!active) return;
      waiting.current = next.authed && next.commands.some(busy);
      setControl(next);
    });
    return () => { active = false; };
  }, []);

  const pending = control?.authed ? control.commands.some(busy) : false;
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [pending, reload]);

  const onSent = useCallback(() => { waiting.current = true; void reload(); }, [reload]);

  const aside = control?.authed ? (
    <button onClick={async () => { await logout(); await reload(); }} className="hover:text-ink">Salir</button>
  ) : "protegido";

  return (
    <Panel title="Control" aside={aside}>
      {control === null ? <Empty>Cargando…</Empty>
        : !control.configured ? <NotConfigured />
        : !control.authed ? <Login onDone={reload} />
        : (
          <div>
            <AggressivenessForm state={state} live={live} disabled={pending} onSent={onSent} />
            <ManualTradeForm live={live} markets={markets} disabled={pending} onSent={onSent} />
            <OpenManualList live={live} disabled={pending} onSent={onSent} />
            <CommandLog commands={control.commands} />
          </div>
        )}
    </Panel>
  );
}

function NotConfigured() {
  return (
    <p className="px-3 py-3 text-[12px] leading-5 text-ink-muted">
      Los controles están apagados en este despliegue. Para activarlos, define en Vercel
      <code className="num mx-1 text-ink">CONTROL_PASSWORD</code>,
      <code className="num mx-1 text-ink">CONTROL_SESSION_SECRET</code> (32+ caracteres) y
      <code className="num mx-1 text-ink">DASHBOARD_OPERATOR_URL</code>.
    </p>
  );
}

function Login({ onDone }: { onDone: () => Promise<void> }) {
  const [result, action, pendingLogin] = useActionState(async (prev: Awaited<ReturnType<typeof login>> | null, form: FormData) => {
    const next = await login(prev, form);
    if (next.ok) await onDone();
    return next;
  }, null);
  return (
    <form action={action} className="flex flex-col gap-2 px-3 py-3">
      <label htmlFor="control-password" className="text-[11px] text-ink-muted">
        Contraseña para cambiar la agresividad u operar a mano
      </label>
      <div className="flex gap-2">
        <input id="control-password" name="password" type="password" autoComplete="current-password" required
          className="num min-w-0 flex-1 rounded-[3px] border border-line-strong bg-bg px-2 py-1.5 text-[13px] outline-none focus:border-series-bot" />
        <button type="submit" disabled={pendingLogin}
          className="rounded-[3px] bg-series-bot px-3 text-[12px] font-medium text-white disabled:opacity-50">
          {pendingLogin ? "…" : "Entrar"}
        </button>
      </div>
      {result && !result.ok ? <p role="alert" className="text-[12px] text-down">{result.error}</p> : null}
    </form>
  );
}

const STATUS = {
  pendiente: { label: "en cola", className: "text-warn" },
  ejecutando: { label: "ejecutando", className: "text-warn" },
  hecha: { label: "hecha", className: "text-up" },
  rechazada: { label: "rechazada", className: "text-down" },
  error: { label: "error", className: "text-down" },
} as const;

function describe(c: Command): string {
  const p = c.payload as Record<string, string | number>;
  if (c.kind === "agresividad") return `Agresividad ${p.bot} ×${p.valor}`;
  if (c.kind === "abrir") return `Abrir ${p.simbolo} ${p.lado} · riesgo ${p.riesgo_pct}% · stop ${p.stop_pct}%`;
  return `Cerrar posición #${p.posicion_id}`;
}

function CommandLog({ commands }: { commands: Command[] }) {
  if (commands.length === 0) return null;
  return (
    <section className="border-t border-line">
      <h3 className="bg-panel-raised px-3 py-1 text-[11px] uppercase tracking-[0.08em] text-ink-faint">Órdenes recientes</h3>
      <ul className="text-[12px]">
        {commands.slice(0, 6).map((c) => (
          <li key={c.id} className="border-t border-line px-3 py-1.5 first:border-t-0">
            <div className="flex items-baseline gap-2">
              <span className="min-w-0 flex-1 truncate">{describe(c)}</span>
              <span className={`shrink-0 text-[11px] font-medium ${STATUS[c.status].className}`}>{STATUS[c.status].label}</span>
            </div>
            <div className="num truncate text-[11px] text-ink-faint" title={c.result ?? undefined}>
              {utc(c.created_at)} UTC{c.result ? ` · ${c.result}` : busy(c) ? " · el bot la toma en menos de 1 min" : ""}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
