import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { AlertCreate, AlertRangeCreate, AlertUpdate } from "../types/api";

export const queryKeys = {
  quote: (symbol: string) => ["quote", symbol] as const,
  candles: (symbol: string) => ["candles", symbol] as const,
  marketStatus: ["market-status"] as const,
  alerts: ["alerts"] as const,
  notifications: ["notifications"] as const,
};

/** Latest price. The WebSocket keeps this fresh; polling is only a fallback. */
export function useQuote(symbol: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.quote(symbol),
    queryFn: () => api.quote(symbol),
    refetchInterval: live ? false : 10_000,
    retry: 1,
  });
}

export function useCandles(symbol: string) {
  return useQuery({
    queryKey: queryKeys.candles(symbol),
    queryFn: () => api.candles(symbol),
    refetchInterval: 60_000,
  });
}

export function useMarketStatus() {
  return useQuery({
    queryKey: queryKeys.marketStatus,
    queryFn: api.marketStatus,
    refetchInterval: 60_000,
  });
}

export function useAlerts() {
  return useQuery({ queryKey: queryKeys.alerts, queryFn: api.alerts });
}

export function useNotifications() {
  return useQuery({ queryKey: queryKeys.notifications, queryFn: api.notifications });
}

export function useCreateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AlertCreate) => api.createAlert(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.alerts }),
  });
}

export function useCreateRangeAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AlertRangeCreate) => api.createRangeAlert(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.alerts }),
  });
}

export function useUpdateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AlertUpdate }) => api.updateAlert(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.alerts }),
  });
}

export function useDeleteAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.alerts }),
  });
}
