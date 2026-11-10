"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { base, fetchTickers, openStream, pair } from "@/lib/binance";

export type Ticker = { price: number; change24h: number; at: number };

type LiveMarket = {
  tickers: Record<string, Ticker>;
  connected: boolean;
  selected: string;
  select: (symbol: string) => void;
};

const Context = createContext<LiveMarket>({ tickers: {}, connected: false, selected: "BTC", select: () => {} });

export const useLiveMarket = () => useContext(Context);

/** Último precio en vivo de una moneda, o el publicado por el bot si todavía no llegó el websocket. */
export function useLivePrice(symbol: string, fallback?: number | null): number | null {
  const { tickers } = useLiveMarket();
  return tickers[base(symbol)]?.price ?? fallback ?? null;
}

// El websocket manda un ticker por segundo por moneda: se juntan y se pinta una vez por segundo.
const FLUSH_MS = 1000;
// Los datos del bot (capital, posiciones, curvas) se publican cada hora; se vuelven a pedir cada minuto.
const REFRESH_MS = 60_000;

export function LiveMarketProvider({ symbols, children }: { symbols: string[]; children: ReactNode }) {
  const [tickers, setTickers] = useState<Record<string, Ticker>>({});
  const [connected, setConnected] = useState(false);
  const [selected, setSelected] = useState(() => base(symbols[0] ?? "BTC"));
  const key = symbols.map(base).join(",");

  useEffect(() => {
    const pending: Record<string, Ticker> = {};
    const streams = key.split(",").filter(Boolean).map((s) => `${pair(s).toLowerCase()}@miniTicker`);
    if (streams.length === 0) return;
    const abort = new AbortController();
    // Foto inicial por REST; el websocket la va pisando. Si llega tarde, no reemplaza datos más nuevos.
    fetchTickers(key.split(","), abort.signal)
      .then((seed) => setTickers((prev) => ({ ...seed, ...prev })))
      .catch(() => {});
    const close = openStream(streams, (_, d) => {
      const price = Number(d.c);
      const open = Number(d.o);
      pending[base(String(d.s))] = { price, change24h: open > 0 ? price / open - 1 : 0, at: Number(d.E) };
    }, setConnected);
    const timer = setInterval(() => {
      if (Object.keys(pending).length === 0) return;
      const batch = { ...pending };
      for (const k of Object.keys(pending)) delete pending[k];
      setTickers((prev) => ({ ...prev, ...batch }));
    }, FLUSH_MS);
    return () => { abort.abort(); close(); clearInterval(timer); };
  }, [key]);

  const value = useMemo(() => ({ tickers, connected, selected, select: setSelected }), [tickers, connected, selected]);
  return (
    <Context value={value}>
      <AutoRefresh />
      {children}
    </Context>
  );
}

/** Vuelve a pedir los datos del servidor cada minuto mientras la pestaña está visible, y al volver a ella. */
function AutoRefresh() {
  const router = useRouter();
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === "visible") router.refresh(); };
    const timer = setInterval(refresh, REFRESH_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [router]);
  return null;
}

/** Indicador de conexión para la barra de estado. */
export function LiveBadge() {
  const { connected } = useLiveMarket();
  return (
    <span className={`flex items-center gap-1.5 ${connected ? "text-ink" : "text-ink-faint"}`}>
      <span className={`size-1.5 rounded-full ${connected ? "bg-up" : "bg-ink-faint"}`} />
      {connected ? "Precios en vivo" : "Conectando…"}
    </span>
  );
}
