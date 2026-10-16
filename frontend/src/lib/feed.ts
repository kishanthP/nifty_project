import type { ConnectionState } from "../hooks/useLiveFeed";
import type { Quote } from "../types/api";
import { secondsSince } from "./format";

const STALE_AFTER_SECONDS = 30;

export type FeedBadge = { label: string; tone: "live" | "warn" | "muted" };

/** What the status pill next to the price should say. */
export function feedBadge(quote: Quote | null, connection: ConnectionState, now: number): FeedBadge {
  if (connection !== "open") return { label: "Reconnecting…", tone: "warn" };
  if (!quote) return { label: "Waiting for data", tone: "muted" };
  if (quote.market_status === "closed") return { label: "Market closed", tone: "muted" };
  if (secondsSince(quote.received_at, now) > STALE_AFTER_SECONDS) return { label: "Delayed", tone: "warn" };
  return { label: "Live", tone: "live" };
}
