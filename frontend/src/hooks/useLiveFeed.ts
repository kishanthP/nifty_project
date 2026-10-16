import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../auth/context";
import { wsUrl } from "../config/env";
import type { AlertTriggeredEvent, LiveMessage } from "../types/api";
import { queryKeys } from "./queries";

export type ConnectionState = "connecting" | "open" | "closed";

/**
 * One WebSocket for the whole dashboard: live prices go straight into the
 * TanStack Query cache, and alert events call `onAlert`. Reconnects with backoff.
 */
export function useLiveFeed(onAlert: (event: AlertTriggeredEvent) => void): ConnectionState {
  const queryClient = useQueryClient();
  const { user, getToken } = useAuth();
  const [state, setState] = useState<ConnectionState>("connecting");
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let pingTimer: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      setState("connecting");
      socket = new WebSocket(wsUrl);

      socket.onopen = async () => {
        attempt = 0;
        setState("open");
        const token = await getToken();
        if (token && socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "auth", token }));
        }
        pingTimer = setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
        }, 25_000);
      };

      socket.onmessage = (event) => {
        let message: LiveMessage;
        try {
          message = JSON.parse(event.data as string) as LiveMessage;
        } catch {
          return;
        }
        if (message.type === "quote") {
          queryClient.setQueryData(queryKeys.quote(message.data.symbol), message.data);
        } else if (message.type === "alert_triggered") {
          onAlertRef.current(message.data);
        }
      };

      socket.onclose = () => {
        clearInterval(pingTimer);
        if (stopped) return;
        setState("closed");
        const delay = Math.min(30_000, 1000 * 2 ** attempt) * (0.8 + Math.random() * 0.4);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      clearInterval(pingTimer);
      socket?.close();
    };
    // Reconnect when the signed-in user changes so the server knows who we are.
  }, [user?.uid, getToken, queryClient]);

  return state;
}
