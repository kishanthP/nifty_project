import {
  AreaSeries,
  ColorType,
  createChart,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { useCandles } from "../hooks/queries";
import { usePrefersDark } from "../hooks/useNow";
import { formatPrice } from "../lib/format";
import type { Alert, Quote } from "../types/api";

// The chart library shows timestamps as UTC; shifting by +5:30 makes the axis read in IST.
const IST_OFFSET_SECONDS = 19_800;

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function withAlpha(hex: string, alpha: number): string {
  const value = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(value.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

interface Props {
  symbol: string;
  quote: Quote | null;
  alerts: Alert[];
}

export default function PriceChart({ symbol, quote, alerts }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const lastTimeRef = useRef(0);
  const dark = usePrefersDark();
  const { data: candles, isPending } = useCandles(symbol);

  // Create the chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      // Keep the TradingView logo: lightweight-charts' license requires attribution.
      layout: { background: { type: ColorType.Solid, color: "transparent" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      crosshair: { horzLine: { labelVisible: true }, vertLine: { labelVisible: true } },
      localization: { priceFormatter: (price: number) => formatPrice(price) },
    });
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(AreaSeries, { lineWidth: 2, priceLineVisible: true });
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      priceLinesRef.current = [];
      lastTimeRef.current = 0;
    };
  }, []);

  // Colors follow light/dark mode.
  useEffect(() => {
    const accent = cssVar("--accent");
    chartRef.current?.applyOptions({
      layout: { textColor: cssVar("--muted") },
      grid: {
        vertLines: { color: withAlpha(cssVar("--border"), 0.5) },
        horzLines: { color: withAlpha(cssVar("--border"), 0.5) },
      },
    });
    seriesRef.current?.applyOptions({
      lineColor: accent,
      topColor: withAlpha(accent, 0.28),
      bottomColor: withAlpha(accent, 0.02),
    });
  }, [dark]);

  // Load the day's 1-minute closes.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !candles) return;
    const data = candles.map((c) => ({ time: (c.time + IST_OFFSET_SECONDS) as UTCTimestamp, value: c.close }));
    series.setData(data);
    lastTimeRef.current = data.length ? data[data.length - 1].time : 0;
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Extend the line with each live tick while the market is open.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !quote || quote.market_status !== "open" || lastTimeRef.current === 0) return;
    const stamp = Date.parse(quote.exchange_ts ?? quote.received_at) / 1000;
    const minute = Math.floor(stamp / 60) * 60 + IST_OFFSET_SECONDS;
    if (minute < lastTimeRef.current) return;
    series.update({ time: minute as UTCTimestamp, value: quote.ltp });
    lastTimeRef.current = minute;
  }, [quote]);

  // Dashed lines at each active alert's price.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const line of priceLinesRef.current) series.removePriceLine(line);
    priceLinesRef.current = alerts.map((alert) =>
      series.createPriceLine({
        price: alert.target_price,
        color: cssVar(alert.condition === "above" ? "--up" : "--down"),
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: alert.condition === "above" ? "▲ alert" : "▼ alert",
      }),
    );
  }, [alerts, dark]);

  return (
    <section className="card p-4 sm:p-5" aria-label="Intraday chart">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted">Intraday · 1 minute</h2>
        {alerts.length > 0 && (
          <span className="text-xs text-muted">Dashed lines = your active alerts</span>
        )}
      </div>
      <div className="relative h-72 sm:h-80">
        <div ref={containerRef} className="absolute inset-0" />
        {!isPending && (!candles || candles.length === 0) && (
          <p className="absolute inset-0 flex items-center justify-center text-sm text-muted">
            Chart data appears once the market worker has fetched today's candles.
          </p>
        )}
      </div>
    </section>
  );
}
