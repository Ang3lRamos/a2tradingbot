"use client";

import {
  CandlestickSeries, ColorType, createChart, createSeriesMarkers, CrosshairMode, HistogramSeries, LineStyle,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { fetchCandles, INTERVAL_SECONDS, klineToCandle, openStream, pair, type Interval } from "@/lib/binance";

export type ChartLine = { price: number; label: string; tone: "up" | "down" | "neutral" | "bot"; dashed?: boolean };
export type ChartMarker = { at: string; side: "long" | "short"; kind: "entry" | "exit"; text?: string };

/** El canvas no entiende var(--x): se leen los tokens del tema una vez montado. */
function palette() {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    panel: v("--panel"), line: v("--line"), lineStrong: v("--line-strong"), ink: v("--ink"), faint: v("--ink-faint"),
    muted: v("--ink-muted"), up: v("--up"), down: v("--down"), bot: v("--series-bot"),
    font: `${v("--font-plex-mono")}, ui-monospace, monospace`,
  };
}

const TONE = { up: "up", down: "down", neutral: "muted", bot: "bot" } as const;

/** Velas de Binance que se actualizan en vivo por websocket, con líneas de precio (entrada, stop) y marcas de operaciones. */
export function CandleChart({ symbol, interval, lines = [], markers = [], compact = false, bars = 300 }: {
  symbol: string;
  interval: Interval;
  lines?: ChartLine[];
  markers?: ChartMarker[];
  compact?: boolean;
  bars?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<{ chart: IChartApi; candles: ISeriesApi<"Candlestick">; markers: ISeriesMarkersPluginApi<Time> } | null>(null);
  const [status, setStatus] = useState<"cargando" | "listo" | "error">("cargando");
  const [version, setVersion] = useState(0); // cambia cuando hay un gráfico nuevo, para volver a dibujar líneas y marcas

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const c = palette();
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: c.panel }, textColor: c.faint, fontSize: 11,
        fontFamily: c.font, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: c.line } },
      rightPriceScale: { borderColor: c.lineStrong, scaleMargins: { top: 0.08, bottom: compact ? 0.06 : 0.22 } },
      timeScale: { borderColor: c.lineStrong, timeVisible: interval !== "1d", secondsVisible: false, rightOffset: 4,
        visible: !compact },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: c.faint, labelBackgroundColor: c.lineStrong },
        horzLine: { color: c.faint, labelBackgroundColor: c.lineStrong } },
      handleScroll: !compact,
      handleScale: !compact,
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: c.up, downColor: c.down, borderVisible: false, wickUpColor: c.up, wickDownColor: c.down,
      priceLineColor: c.muted, priceLineStyle: LineStyle.Dotted,
      // En los mini gráficos solo se rotulan la entrada y el stop: el precio ya está arriba en cifras.
      lastValueVisible: !compact,
    });
    const volume = compact ? null : chart.addSeries(HistogramSeries, {
      priceScaleId: "volumen", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false,
    });
    volume?.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    // Hex con alfa (≈35%): el canvas no siempre acepta color-mix.
    const volumeColor = (open: number, close: number) => `${close >= open ? c.up : c.down}59`;

    chartRef.current = { chart, candles, markers: createSeriesMarkers(candles, []) };
    setStatus("cargando");
    setVersion((n) => n + 1);

    const abort = new AbortController();
    let ready = false;
    let close = () => {};
    fetchCandles(symbol, interval, bars, abort.signal)
      .then((rows) => {
        candles.setData(rows.map((r) => ({ ...r, time: r.time as UTCTimestamp })));
        volume?.setData(rows.map((r) => ({ time: r.time as UTCTimestamp, value: r.volume, color: volumeColor(r.open, r.close) })));
        ready = true;
        setStatus("listo");
        close = openStream([`${pair(symbol).toLowerCase()}@kline_${interval}`], (_, d) => {
          const k = klineToCandle(d.k as Record<string, unknown>);
          const time = k.time as UTCTimestamp;
          candles.update({ ...k, time });
          volume?.update({ time, value: k.volume, color: volumeColor(k.open, k.close) });
        }, () => {});
      })
      .catch((err: unknown) => { if (!abort.signal.aborted && !ready) { console.error(err); setStatus("error"); } });

    return () => {
      abort.abort();
      close();
      chartRef.current = null;
      chart.remove();
    };
  }, [symbol, interval, compact, bars]);

  // Líneas de precio: se reemplazan enteras cuando cambian.
  const linesKey = JSON.stringify(lines);
  useEffect(() => {
    const ref = chartRef.current;
    if (!ref) return;
    const c = palette();
    const created: IPriceLine[] = (JSON.parse(linesKey) as ChartLine[]).map((l) => ref.candles.createPriceLine({
      price: l.price, title: compact ? "" : l.label, color: c[TONE[l.tone]], lineWidth: 1,
      lineStyle: l.dashed ? LineStyle.Dashed : LineStyle.Solid, axisLabelVisible: true,
    }));
    return () => { for (const line of created) ref.candles.removePriceLine(line); };
  }, [linesKey, version, compact]);

  // Marcas de entrada y salida, ajustadas al inicio de la vela que las contiene.
  const markersKey = JSON.stringify(markers);
  useEffect(() => {
    const ref = chartRef.current;
    if (!ref) return;
    const c = palette();
    const step = INTERVAL_SECONDS[interval];
    const list: SeriesMarker<Time>[] = (JSON.parse(markersKey) as ChartMarker[])
      .map((m) => {
        const t = Math.floor(new Date(m.at).getTime() / 1000 / step) * step;
        const buy = (m.side === "long") === (m.kind === "entry");
        return {
          time: t as UTCTimestamp,
          position: buy ? "belowBar" : "aboveBar",
          shape: m.kind === "entry" ? (buy ? "arrowUp" : "arrowDown") : "circle",
          color: m.kind === "entry" ? (m.side === "long" ? c.up : c.down) : c.muted,
          text: compact ? undefined : m.text,
        } satisfies SeriesMarker<Time>;
      })
      .sort((a, b) => Number(a.time) - Number(b.time));
    ref.markers.setMarkers(list);
  }, [markersKey, version, interval, compact]);

  return (
    <div className="relative h-full w-full">
      <div ref={container} className="absolute inset-0" />
      {status !== "listo" ? (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-[12px] text-ink-faint">
          {status === "cargando" ? "Cargando velas…" : "No se pudieron cargar las velas de Binance."}
        </div>
      ) : null}
    </div>
  );
}
