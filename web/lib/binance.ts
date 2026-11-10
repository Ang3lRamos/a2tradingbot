// Datos públicos de Binance futuros (perpetuos USDT), leídos desde el navegador del visitante.
// Sin claves: solo velas y tickers públicos. El servidor de Vercel no los pide (Binance bloquea algunas regiones).

const REST = "https://fapi.binance.com/fapi/v1";
const STREAM = "wss://fstream.binance.com/market/stream";

export type Interval = "15m" | "1h" | "4h" | "1d";

export const INTERVAL_SECONDS: Record<Interval, number> = { "15m": 900, "1h": 3600, "4h": 14_400, "1d": 86_400 };

/** Vela con tiempo de apertura en segundos UTC, el formato que usa lightweight-charts. */
export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };

/** "BTC/USDT:USDT" o "BTC" → "BTCUSDT". */
export function pair(symbol: string): string {
  const p = symbol.split(":")[0].replace("/", "").toUpperCase();
  return p.endsWith("USDT") ? p : `${p}USDT`;
}

/** "BTC/USDT:USDT" → "BTC". */
export function base(symbol: string): string {
  return symbol.split("/")[0].replace(/USDT$/, "");
}

export async function fetchCandles(symbol: string, interval: Interval, limit = 300, signal?: AbortSignal): Promise<Candle[]> {
  const res = await fetch(`${REST}/klines?symbol=${pair(symbol)}&interval=${interval}&limit=${limit}`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`Binance respondió ${res.status}`);
  const rows = (await res.json()) as (string | number)[][];
  return rows.map((r) => ({
    time: Number(r[0]) / 1000, open: Number(r[1]), high: Number(r[2]), low: Number(r[3]), close: Number(r[4]), volume: Number(r[5]),
  }));
}

/** Último precio y cambio de 24 h por par, para pintar algo antes de que conecte el websocket. */
export async function fetchTickers(symbols: string[], signal?: AbortSignal): Promise<Record<string, { price: number; change24h: number; at: number }>> {
  const res = await fetch(`${REST}/ticker/24hr`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`Binance respondió ${res.status}`);
  const wanted = new Set(symbols.map(pair));
  const rows = (await res.json()) as { symbol: string; lastPrice: string; priceChangePercent: string; closeTime: number }[];
  return Object.fromEntries(rows.filter((r) => wanted.has(r.symbol)).map((r) => [
    base(r.symbol), { price: Number(r.lastPrice), change24h: Number(r.priceChangePercent) / 100, at: r.closeTime },
  ]));
}

type Handler = (stream: string, data: Record<string, unknown>) => void;

/**
 * Websocket combinado que se reconecta solo (espera creciente, hasta 30 s).
 * Devuelve una función para cerrarlo.
 */
export function openStream(streams: string[], onMessage: Handler, onStatus: (connected: boolean) => void): () => void {
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let closed = false;

  const connect = () => {
    socket = new WebSocket(`${STREAM}?streams=${streams.join("/")}`);
    socket.onopen = () => { attempt = 0; onStatus(true); };
    socket.onmessage = (event) => {
      const msg = JSON.parse(String(event.data)) as { stream: string; data: Record<string, unknown> };
      if (msg.stream) onMessage(msg.stream, msg.data);
    };
    socket.onclose = () => {
      onStatus(false);
      if (closed) return;
      retry = setTimeout(connect, Math.min(30_000, 1000 * 2 ** attempt++));
    };
    socket.onerror = () => socket?.close();
  };

  connect();
  return () => {
    closed = true;
    clearTimeout(retry);
    socket?.close();
  };
}

export function klineToCandle(k: Record<string, unknown>): Candle {
  return {
    time: Number(k.t) / 1000, open: Number(k.o), high: Number(k.h), low: Number(k.l), close: Number(k.c), volume: Number(k.v),
  };
}
