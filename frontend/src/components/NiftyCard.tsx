import { useEffect, useRef, useState } from "react";

import { useMarketStatus } from "../hooks/queries";
import type { ConnectionState } from "../hooks/useLiveFeed";
import { useNow } from "../hooks/useNow";
import {
  formatNextOpen,
  formatPercent,
  formatPrice,
  formatSigned,
  sourceLabel,
  timeAgo,
} from "../lib/format";
import { feedBadge } from "../lib/feed";
import type { Quote } from "../types/api";
import { ArrowDownIcon, ArrowUpIcon } from "./icons";
import StatusBadge from "./StatusBadge";

interface Props {
  quote: Quote | null;
  loading: boolean;
  error: Error | null;
  connection: ConnectionState;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export default function NiftyCard({ quote, loading, error, connection }: Props) {
  const now = useNow(1000);
  const marketStatus = useMarketStatus().data;

  // Briefly flash green/red when the price ticks up/down.
  const previous = useRef<number | null>(null);
  const [flash, setFlash] = useState<{ dir: "up" | "down"; key: number } | null>(null);
  useEffect(() => {
    if (!quote) return;
    const last = previous.current;
    previous.current = quote.ltp;
    if (last !== null && quote.ltp !== last) {
      setFlash({ dir: quote.ltp > last ? "up" : "down", key: Date.now() });
    }
  }, [quote]);

  const change = quote?.change ?? null;
  const tone = change == null || change === 0 ? "text-muted" : change > 0 ? "text-up" : "text-down";

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="nifty-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 id="nifty-title" className="text-sm font-semibold tracking-wide text-muted">
            {quote?.name ?? "NIFTY 50"} <span className="font-normal">· NSE INDEX</span>
          </h2>
        </div>
        <StatusBadge badge={feedBadge(quote, connection, now)} />
      </div>

      {quote ? (
        <>
          <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-1">
            <span
              key={flash?.key}
              className={`-mx-1 rounded-md px-1 text-4xl font-semibold tabular-nums sm:text-5xl ${
                flash ? `flash-${flash.dir}` : ""
              }`}
              aria-live="polite"
            >
              {formatPrice(quote.ltp)}
            </span>
            <span className={`mb-1 inline-flex items-center gap-1 text-lg font-medium tabular-nums ${tone}`}>
              {change != null && change > 0 && <ArrowUpIcon />}
              {change != null && change < 0 && <ArrowDownIcon />}
              {formatSigned(change)} ({formatPercent(quote.change_pct)})
            </span>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Open" value={formatPrice(quote.open)} />
            <Stat label="High" value={formatPrice(quote.high)} />
            <Stat label="Low" value={formatPrice(quote.low)} />
            <Stat label="Prev. close" value={formatPrice(quote.prev_close)} />
          </dl>

          <p className="mt-5 text-xs text-muted">
            Updated {timeAgo(quote.received_at, now)} · Source: {sourceLabel(quote.source)}
            {marketStatus && !marketStatus.is_open && (
              <>
                {" "}
                · NSE {marketStatus.holiday_name ? `holiday (${marketStatus.holiday_name})` : "closed"},
                opens {formatNextOpen(marketStatus.next_open)}
              </>
            )}
          </p>
        </>
      ) : (
        <div className="mt-4 text-muted">
          {loading ? (
            <div className="h-12 w-56 animate-pulse rounded-lg bg-surface-2" />
          ) : (
            <p className="text-sm">
              {error?.message ?? "No price yet."} The market worker publishes the first price a few
              seconds after it starts.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
