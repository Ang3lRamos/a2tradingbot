"use client";

import { useSyncExternalStore } from "react";

import { ago } from "@/lib/format";

// El bot corre un ciclo por hora: sin ciclo en 75 minutos se considera caído.
const ALIVE_MINUTES = 75;
const TICK_MS = 30_000;

// Reloj como fuente externa: cambia cada 30 s (el valor es estable dentro de cada tramo).
function subscribe(onTick: () => void) {
  const timer = setInterval(onTick, TICK_MS);
  return () => clearInterval(timer);
}
const clientNow = () => Math.floor(Date.now() / TICK_MS) * TICK_MS;
const serverNow = () => null; // en el servidor no se sabe cuándo lo verá el usuario

/** Estado del bot calculado en el navegador: los datos publicados no saben cuánto tiempo pasó desde entonces. */
export function Heartbeat({ lastCycle }: { lastCycle: string | null | undefined }) {
  const now = useSyncExternalStore(subscribe, clientNow, serverNow);

  if (now === null) return <span className="text-ink-faint">…</span>;
  const minutes = lastCycle ? (now - new Date(lastCycle).getTime()) / 60_000 : null;
  const alive = minutes !== null && minutes < ALIVE_MINUTES;

  return (
    <span className="flex items-center gap-1.5">
      <span className={`relative inline-flex size-2 rounded-full ${alive ? "bg-up" : "bg-down"}`}>
        {alive ? <span className="absolute inset-0 animate-ping rounded-full bg-up opacity-50" /> : null}
      </span>
      <span className={alive ? "text-ink" : "text-down"}>{alive ? "Activo" : "Sin señal de vida"}</span>
      <span className="text-ink-faint">· {ago(minutes)}</span>
    </span>
  );
}
