const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const istDateTime = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});

const istTime = new Intl.DateTimeFormat("en-IN", {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "Asia/Kolkata",
});

const istWeekdayTime = new Intl.DateTimeFormat("en-IN", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});

/** 22563.4 → "22,563.40" (Indian digit grouping: 1234567 → "12,34,567.00"). */
export function formatPrice(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "—" : inr.format(value);
}

/** 13.4 → "+13.40", -5 → "−5.00" */
export function formatSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${inr.format(Math.abs(value))}`;
}

/** 0.0594 → "+0.06%" */
export function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

export function formatDateTime(iso: string): string {
  return istDateTime.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return istTime.format(new Date(iso));
}

export function formatNextOpen(iso: string): string {
  return istWeekdayTime.format(new Date(iso));
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatDateTime(iso);
}

export function secondsSince(iso: string, now: number = Date.now()): number {
  return (now - new Date(iso).getTime()) / 1000;
}

const SOURCE_LABELS: Record<string, string> = {
  angelone: "Angel One",
  yahoo: "Yahoo Finance",
  mock: "Mock data",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
