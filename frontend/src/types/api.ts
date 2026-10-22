export type MarketState = "open" | "closed";

export interface Quote {
  symbol: string;
  name: string;
  ltp: number;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  change: number | null;
  change_pct: number | null;
  exchange_ts: string | null;
  received_at: string;
  source: string;
  market_status: MarketState;
}

export interface Candle {
  time: number; // Unix seconds (UTC)
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface MarketStatus {
  is_open: boolean;
  reason: "open" | "weekend" | "holiday" | "pre_open" | "after_hours";
  holiday_name: string | null;
  next_open: string;
}

export type AlertCondition = "above" | "below";
export type AlertStatus = "active" | "triggered" | "cancelled";

export interface Alert {
  id: string;
  symbol: string;
  instrument_name: string;
  condition: AlertCondition;
  target_price: number;
  base_price: number | null;
  status: AlertStatus;
  note: string | null;
  triggered_at: string | null;
  triggered_price: number | null;
  /** Set when the alert is one side of a "High & low" pair. */
  group_id: string | null;
  one_cancels_other: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertRangeCreate {
  symbol: string;
  high_price: number;
  low_price: number;
  one_cancels_other: boolean;
  note?: string;
}

export interface AlertBatchCreate {
  symbol: string;
  items: { target_price: number; condition?: AlertCondition }[];
  note?: string;
}

export interface AlertCreate {
  symbol: string;
  target_price: number;
  condition?: AlertCondition;
  note?: string;
}

export interface AlertUpdate {
  target_price?: number;
  condition?: AlertCondition;
  note?: string;
  status?: "active" | "cancelled";
}

export interface NotificationItem {
  id: string;
  alert_id: string | null;
  channel: string;
  title: string;
  body: string;
  status: "pending" | "sent" | "failed";
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface User {
  id: string;
  email: string | null;
  display_name: string | null;
  photo_url: string | null;
  created_at: string;
}

export interface TestPushResult {
  channel: string;
  devices: number;
  delivered: number;
  error: string | null;
}

export interface AlertTriggeredEvent {
  alert_id: string;
  notification_id: string;
  symbol: string;
  condition: AlertCondition;
  target_price: number;
  triggered_price: number;
  title: string;
  body: string;
}

export type LiveMessage =
  | { type: "quote"; data: Quote }
  | { type: "alert_triggered"; data: AlertTriggeredEvent }
  | { type: "auth_ok" }
  | { type: "auth_error"; detail: string }
  | { type: "pong" };
