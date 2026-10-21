import { config } from "../config/env";
import type {
  Alert,
  AlertCreate,
  AlertRangeCreate,
  AlertUpdate,
  Candle,
  MarketStatus,
  NotificationItem,
  Quote,
  TestPushResult,
  User,
} from "../types/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type TokenProvider = () => Promise<string | null>;
let tokenProvider: TokenProvider | null = null;

/** The auth layer registers how to get the current login token. */
export function setTokenProvider(provider: TokenProvider | null): void {
  tokenProvider = provider;
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI validation errors: [{ msg: "Value error, ..." }, ...]
    return detail
      .map((item) => String((item as { msg?: string }).msg ?? "").replace(/^Value error, /, ""))
      .join(". ");
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const { auth = true, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (rest.body) headers.set("Content-Type", "application/json");
  if (auth && tokenProvider) {
    const token = await tokenProvider();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${config.apiUrl}/api/v1${path}`, { ...rest, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, errorMessage(body, response.statusText || "Request failed"));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  me: () => request<User>("/me"),
  quote: (symbol: string) => request<Quote>(`/market/quote/${symbol}`, { auth: false }),
  candles: (symbol: string) => request<Candle[]>(`/market/candles/${symbol}`, { auth: false }),
  marketStatus: () => request<MarketStatus>("/market/status", { auth: false }),

  alerts: () => request<Alert[]>("/alerts"),
  createAlert: (body: AlertCreate) => request<Alert>("/alerts", { method: "POST", body: json(body) }),
  createRangeAlert: (body: AlertRangeCreate) =>
    request<Alert[]>("/alerts/range", { method: "POST", body: json(body) }),
  updateAlert: (id: string, body: AlertUpdate) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: json(body) }),
  deleteAlert: (id: string) => request<void>(`/alerts/${id}`, { method: "DELETE" }),

  notifications: () => request<NotificationItem[]>("/notifications?limit=10"),

  registerDevice: (token: string, userAgent: string) =>
    request<void>("/devices", { method: "POST", body: json({ token, user_agent: userAgent }) }),
  unregisterDevice: (token: string) =>
    request<void>("/devices/unregister", { method: "POST", body: json({ token }) }),
  testPush: () => request<TestPushResult>("/devices/test", { method: "POST" }),
};
