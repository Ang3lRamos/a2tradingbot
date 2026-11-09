"use client";

import { useEffect, useState } from "react";

import { ago } from "@/lib/format";

// El bot corre un ciclo por hora: sin ciclo en 75 minutos se considera caído.
const ALIVE_MINUTES = 75;

/** Estado del bot calculado en el navegador: los datos publicados no saben cuánto tiempo pasó desde entonces. */
export function Heartbeat({ lastCycle }: { lastCycle: string | null | undefined }) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

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
