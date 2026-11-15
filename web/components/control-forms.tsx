"use client";

import { useState } from "react";

import { closeManual, openManual, setAggressiveness } from "@/app/actions";
import { base } from "@/lib/binance";
import { num, pct, price, tone } from "@/lib/format";
import type { ActionResult, BotState, Live, Market } from "@/lib/types";

import { useLiveMarket } from "./live-market";
import { unrealized } from "./positions-panel";

type Props = { disabled: boolean; onSent: () => void };

const PRESETS = [
  { value: 0.5, label: "Prudente" },
  { value: 1, label: "Backtest" },
  { value: 1.5, label: "Agresivo" },
  { value: 2, label: "Máximo" },
];

const field = "num w-full rounded-[3px] border border-line-strong bg-bg px-2 py-1 text-[13px] outline-none focus:border-series-bot";
const primary = "rounded-[3px] px-3 py-1.5 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-40";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-line">
      <h3 className="bg-panel-raised px-3 py-1 text-[11px] uppercase tracking-[0.08em] text-ink-faint">{title}</h3>
      <div className="px-3 py-2.5">{children}</div>
    </section>
  );
}

function Feedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return result.ok
    ? <p className="mt-1.5 text-[11px] text-ink-muted">Orden enviada: el bot la toma en menos de un minuto.</p>
    : <p role="alert" className="mt-1.5 text-[11px] text-down">{result.error}</p>;
}

// --- agresividad ---

export function AggressivenessForm({ state, live, disabled, onSent }: Props & { state: BotState | null; live: Live | null }) {
  const current = state?.agresividad ?? { rupturas: 1, tendencia: 1 };
  const baseRisk = state?.riesgo_por_operacion ?? 0.003;
  const equity = live?.capital_actual ?? null;
  return (
    <Section title="Agresividad">
      <div className="flex flex-col gap-3">
        <BotDial bot="rupturas" label="Rupturas" current={current.rupturas} disabled={disabled} onSent={onSent}
          effect={(v) => `riesgo ${pct(baseRisk * v, 2, false)} por operación${equity ? ` · ~${num(equity * baseRisk * v, 0)} USDT por stop` : ""}`} />
        <BotDial bot="tendencia" label="Tendencia L/S" current={current.tendencia} disabled={disabled} onSent={onSent}
          effect={(v) => `exposición objetivo ×${v} · nunca más de 100% (sin apalancamiento)`} />
      </div>
      <p className="mt-2.5 text-[11px] leading-4 text-ink-faint">
        ×1 es lo que se probó en el backtest. Otro valor cambia el tamaño, no las señales; las métricas en R siguen
        siendo comparables. En rupturas, con 0,5% de riesgo (×1,67) el backtest cayó 11,8% y activaba el kill switch del 10%.
      </p>
    </Section>
  );
}

function BotDial({ bot, label, current, effect, disabled, onSent }: Props & {
  bot: "rupturas" | "tendencia"; label: string; current: number; effect: (v: number) => string;
}) {
  const [value, setValue] = useState(current);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [sending, setSending] = useState(false);
  const id = `aggr-${bot}`;

  async function apply() {
    setSending(true);
    const next = await setAggressiveness(bot, value);
    setSending(false);
    setResult(next);
    if (next.ok) onSent();
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-[12px] font-medium">{label}</label>
        <span className="num text-[11px] text-ink-faint">
          ahora ×{current}{value !== current ? <span className="text-warn"> → ×{value}</span> : null}
        </span>
      </div>
      <input id={id} type="range" min={0.25} max={2} step={0.25} value={value} disabled={disabled}
        onChange={(e) => { setValue(Number(e.target.value)); setResult(null); }}
        className="mt-1 w-full accent-[var(--series-bot)]" />
      <div className="flex flex-wrap items-center gap-1">
        {PRESETS.map((p) => (
          <button key={p.value} type="button" disabled={disabled} onClick={() => { setValue(p.value); setResult(null); }}
            className={`rounded-[3px] border px-1.5 py-0.5 text-[11px] ${value === p.value ? "border-series-bot text-ink" : "border-line-strong text-ink-muted hover:text-ink"}`}>
            {p.label} ×{p.value}
          </button>
        ))}
        <button type="button" onClick={apply} disabled={disabled || sending || value === current}
          className={`${primary} ml-auto bg-series-bot text-white`}>
          {sending ? "…" : "Aplicar"}
        </button>
      </div>
      <p className={`num mt-1 text-[11px] ${value > 1.5 ? "text-warn" : "text-ink-faint"}`}>{effect(value)}</p>
      <Feedback result={result} />
    </div>
  );
}

// --- operación manual ---

export function ManualTradeForm({ live, markets, disabled, onSent }: Props & { live: Live | null; markets: Market[] }) {
  const { tickers } = useLiveMarket();
  const coins = markets.map((m) => m.simbolo);
  const suggested = (c: string) => Number((markets.find((m) => m.simbolo === c)?.stop_sugerido_pct ?? 2).toFixed(1));
  const [coin, setCoin] = useState(coins[0] ?? "BTC");
  const [side, setSide] = useState<"long" | "short">("long");
  const [riskPct, setRiskPct] = useState(0.3);
  const [stopPct, setStopPct] = useState(() => suggested(coins[0] ?? "BTC"));
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<ActionResult | null>(null);

  const taken = new Set((live?.posiciones_abiertas ?? []).map((p) => base(p.simbolo)));
  const equity = live?.capital_actual ?? null;
  const px = tickers[coin]?.price ?? markets.find((m) => m.simbolo === coin)?.precio ?? null;
  // Misma fórmula que el bot: riesgo fijo hasta el stop, con el nocional topado en 1/3 del capital (1x entre 3 posiciones).
  const qty = equity && px ? Math.min((equity * riskPct) / 100 / (px * stopPct / 100), equity / 3 / px) : null;
  const stopPrice = px ? px * (1 + (side === "long" ? -1 : 1) * stopPct / 100) : null;
  const valid = riskPct >= 0.05 && riskPct <= 2 && stopPct >= 0.2 && stopPct <= 20;
  const blocked = taken.has(coin) ? `Ya hay una posición en ${coin}: el exchange permite una por moneda.` : null;

  function pick(c: string) {
    setCoin(c); setStopPct(suggested(c)); setConfirming(false); setResult(null);
  }

  async function submit() {
    if (!confirming) { setConfirming(true); return; }
    setSending(true);
    const next = await openManual({ coin, side, riskPct, stopPct });
    setSending(false); setConfirming(false); setResult(next);
    if (next.ok) onSent();
  }

  return (
    <Section title="Operación manual · Binance Demo">
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2 flex gap-1" role="radiogroup" aria-label="Moneda">
          {coins.map((c) => (
            <button key={c} type="button" role="radio" aria-checked={coin === c} onClick={() => pick(c)}
              className={`flex-1 rounded-[3px] border py-1 text-[12px] ${coin === c ? "border-series-bot text-ink" : "border-line-strong text-ink-muted"} ${taken.has(c) ? "line-through" : ""}`}>
              {c}
            </button>
          ))}
        </div>
        <div className="col-span-2 grid grid-cols-2 gap-1" role="radiogroup" aria-label="Dirección">
          {(["long", "short"] as const).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={side === s} onClick={() => { setSide(s); setConfirming(false); }}
              className={`rounded-[3px] border py-1 text-[12px] font-medium uppercase ${side === s ? (s === "long" ? "border-up text-up" : "border-down text-down") : "border-line-strong text-ink-muted"}`}>
              {s === "long" ? "▲ long" : "▼ short"}
            </button>
          ))}
        </div>
        <label className="text-[11px] text-ink-muted">
          Riesgo (% del capital)
          <input type="number" min={0.05} max={2} step={0.05} value={riskPct} className={`${field} mt-0.5`}
            onChange={(e) => { setRiskPct(Number(e.target.value)); setConfirming(false); }} />
        </label>
        <label className="text-[11px] text-ink-muted">
          Stop (% del precio)
          <input type="number" min={0.2} max={20} step={0.1} value={stopPct} className={`${field} mt-0.5`}
            onChange={(e) => { setStopPct(Number(e.target.value)); setConfirming(false); }} />
        </label>
      </div>

      <dl className="num mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        <dt className="text-ink-faint">Precio ahora</dt><dd className="text-right">{px ? price(px) : "—"}</dd>
        <dt className="text-ink-faint">Stop</dt><dd className="text-right">{stopPrice ? price(stopPrice) : "—"} <span className="text-ink-faint">(sugerido {suggested(coin)}%)</span></dd>
        <dt className="text-ink-faint">Cantidad ≈</dt><dd className="text-right">{qty ? `${num(qty, 4)} ${coin}` : "—"}</dd>
        <dt className="text-ink-faint">Nocional ≈</dt><dd className="text-right">{qty && px ? `${num(qty * px, 0)} USDT` : "—"}</dd>
        <dt className="text-ink-faint">Si toca el stop</dt>
        <dd className="text-right text-down">{qty && px ? `−${num(qty * px * stopPct / 100, 2)} USDT` : "—"}</dd>
      </dl>

      {blocked ? <p className="mt-2 text-[11px] text-warn">{blocked}</p> : null}
      <button type="button" onClick={submit} disabled={disabled || sending || !valid || Boolean(blocked) || !px}
        className={`${primary} mt-2 w-full text-white ${confirming ? "bg-warn text-bg" : side === "long" ? "bg-up" : "bg-down"}`}>
        {sending ? "…" : confirming ? `Confirmar: ${side.toUpperCase()} ${coin} a mercado` : `Abrir ${side} ${coin}`}
      </button>
      {confirming ? (
        <button type="button" onClick={() => setConfirming(false)} className="mt-1 w-full text-[11px] text-ink-faint hover:text-ink">Cancelar</button>
      ) : null}
      <Feedback result={result} />
      <p className="mt-2 text-[11px] leading-4 text-ink-faint">
        Sale con stop en el exchange y sigue el mismo trailing que el bot. Se cuenta aparte: no entra en las métricas
        de la estrategia, pero sí en el capital y el kill switch de la cuenta.
      </p>
    </Section>
  );
}

export function OpenManualList({ live, disabled, onSent }: Props & { live: Live | null }) {
  const { tickers } = useLiveMarket();
  const [confirming, setConfirming] = useState<number | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const manual = (live?.posiciones_abiertas ?? []).filter((p) => p.origen === "manual");
  if (manual.length === 0) return null;

  async function close(id: number) {
    if (confirming !== id) { setConfirming(id); return; }
    setConfirming(null);
    const next = await closeManual(id);
    setResult(next);
    if (next.ok) onSent();
  }

  return (
    <Section title="Manuales abiertas">
      <ul className="flex flex-col gap-1.5 text-[12px]">
        {manual.map((p) => {
          const coin = base(p.simbolo);
          const px = tickers[coin]?.price;
          const pnl = px != null ? unrealized(p, px) : null;
          return (
            <li key={p.id} className="flex items-center gap-2">
              <span className="font-medium">{coin}</span>
              <span className={`text-[11px] uppercase ${p.lado === "long" ? "text-up" : "text-down"}`}>{p.lado === "long" ? "▲" : "▼"} {p.lado}</span>
              <span className={`num ml-auto ${tone(pnl)}`}>{num(pnl, 2, true)}</span>
              <button type="button" onClick={() => close(p.id)} disabled={disabled}
                className={`${primary} border ${confirming === p.id ? "border-warn text-warn" : "border-line-strong text-ink-muted hover:text-ink"}`}>
                {confirming === p.id ? "¿Cerrar?" : "Cerrar"}
              </button>
            </li>
          );
        })}
      </ul>
      <Feedback result={result} />
    </Section>
  );
}
