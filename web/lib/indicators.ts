// Indicadores con las mismas fórmulas que el bot (src/tradebot/features/indicators.py y strategy.py):
// EMA de pandas con adjust=False, RSI y ATR con suavizado de Wilder, canal de Donchian sin la vela actual.
// Cada valor en t usa solo velas hasta t. `null` = todavía no hay suficientes velas.

import type { Candle } from "./binance";

type Series = (number | null)[];

/** ewm(alpha, adjust=False, min_periods): arranca en el primer valor válido. */
function ewm(values: Series, alpha: number, minPeriods: number): Series {
  const out: Series = [];
  let prev: number | null = null;
  let seen = 0;
  for (const v of values) {
    if (v == null) { out.push(prev != null && seen >= minPeriods ? prev : null); continue; }
    prev = prev == null ? v : (1 - alpha) * prev + alpha * v;
    seen += 1;
    out.push(seen >= minPeriods ? prev : null);
  }
  return out;
}

export function ema(values: number[], period: number): Series {
  return ewm(values, 2 / (period + 1), period);
}

export function rsi(closes: number[], period = 14): Series {
  const delta: Series = closes.map((c, i) => (i === 0 ? null : c - closes[i - 1]));
  const gain = ewm(delta.map((d) => (d == null ? null : Math.max(d, 0))), 1 / period, period);
  const loss = ewm(delta.map((d) => (d == null ? null : Math.max(-d, 0))), 1 / period, period);
  return gain.map((g, i) => {
    const l = loss[i];
    if (g == null || l == null) return null;
    return l === 0 ? 100 : 100 - 100 / (1 + g / l);
  });
}

export function atr(candles: Candle[], period = 14): Series {
  const tr = candles.map((c, i) => {
    const prev = i > 0 ? candles[i - 1].close : null;
    return prev == null ? c.high - c.low : Math.max(c.high - c.low, Math.abs(c.high - prev), Math.abs(c.low - prev));
  });
  return ewm(tr, 1 / period, period);
}

/** Canal de las `lookback` velas ANTERIORES (como el bot): en t no incluye la vela t. */
export function donchian(candles: Candle[], lookback = 20): { upper: Series; lower: Series } {
  const upper: Series = [];
  const lower: Series = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < lookback) { upper.push(null); lower.push(null); continue; }
    const window = candles.slice(i - lookback, i);
    upper.push(Math.max(...window.map((c) => c.high)));
    lower.push(Math.min(...window.map((c) => c.low)));
  }
  return { upper, lower };
}

/** Señal del bot de tendencia: promedio de signo(retorno a 20, 60 y 120 días), entre −1 y +1. */
export function trendSignal(dailyCloses: number[]): { signal: number; parts: Record<number, number> } | null {
  const last = dailyCloses.length - 1;
  if (last < 120) return null;
  const parts = Object.fromEntries([20, 60, 120].map((n) => [n, Math.sign(dailyCloses[last] / dailyCloses[last - n] - 1)]));
  return { signal: (parts[20] + parts[60] + parts[120]) / 3, parts };
}

/** Solo velas cerradas: la última de Binance suele estar en formación. */
export function closedOnly(candles: Candle[], stepSeconds: number, now = Date.now() / 1000): Candle[] {
  return candles.filter((c) => c.time + stepSeconds <= now);
}

const lastValue = (s: Series) => s.at(-1) ?? null;

export type Reading = {
  price: number;
  emaFast: number | null;
  emaSlow: number | null;
  rsi: number | null;
  atrPct: number | null;
  upper: number | null;      // canal de 20 velas de 4h que vigila el bot de rupturas
  lower: number | null;
  trend: ReturnType<typeof trendSignal>;
};

/** Lectura con velas de 4h cerradas (las del bot de rupturas) y diarias (las del bot de tendencia), al precio de ahora. */
export function reading(h4: Candle[], daily: Candle[], price: number): Reading {
  const closes = h4.map((c) => c.close);
  const channel = donchian([...h4, { ...h4.at(-1)!, time: h4.at(-1)!.time + 14_400 }], 20); // canal de la vela en curso
  const lastAtr = lastValue(atr(h4, 14));
  return {
    price,
    emaFast: lastValue(ema(closes, 50)),
    emaSlow: lastValue(ema(closes, 200)),
    rsi: lastValue(rsi(closes, 14)),
    atrPct: lastAtr != null ? lastAtr / closes.at(-1)! : null,
    upper: lastValue(channel.upper),
    lower: lastValue(channel.lower),
    trend: trendSignal(daily.map((c) => c.close)),
  };
}
