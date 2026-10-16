import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/context";
import { config, isPushConfigured } from "../config/env";
import { api } from "../lib/api";
import { getFirebaseApp } from "../lib/firebase";
import { readStorage, writeStorage } from "../lib/storage";

export type PushState =
  | "checking"
  | "not-configured" // VITE_FIREBASE_* / VAPID key missing
  | "unsupported" // browser can't do web push (e.g. iOS Safari outside a home-screen app)
  | "denied" // user blocked notifications in browser settings
  | "off"
  | "on";

const TOKEN_KEY = "share-market.fcm-token";
const SW_PATH = "/firebase-messaging-sw.js";

async function browserSupportsPush(): Promise<boolean> {
  if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    return false;
  }
  const { isSupported } = await import("firebase/messaging");
  return isSupported();
}

/** Ask the browser for a push token (FCM) and save it on the server. */
async function registerToken(): Promise<string> {
  const registration = await navigator.serviceWorker.register(SW_PATH);
  await navigator.serviceWorker.ready;
  const { getMessaging, getToken } = await import("firebase/messaging");
  const token = await getToken(getMessaging(getFirebaseApp()), {
    vapidKey: config.vapidKey,
    serviceWorkerRegistration: registration,
  });
  await api.registerDevice(token, navigator.userAgent.slice(0, 500));
  writeStorage(TOKEN_KEY, token);
  return token;
}

export function usePushNotifications() {
  const { user } = useAuth();
  const [state, setState] = useState<PushState>("checking");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!isPushConfigured) return setState("not-configured");
      if (!(await browserSupportsPush())) return !cancelled && setState("unsupported");
      if (Notification.permission === "denied") return !cancelled && setState("denied");
      if (Notification.permission === "granted" && readStorage(TOKEN_KEY)) {
        if (!cancelled) setState("on");
        // Tokens can rotate; refresh quietly so the server always has the current one.
        registerToken().catch(() => undefined);
        return;
      }
      if (!cancelled) setState("off");
    })();
    return () => {
      cancelled = true;
    };
  }, [user?.uid]);

  const enable = useCallback(async () => {
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState(permission === "denied" ? "denied" : "off");
        return false;
      }
      await registerToken();
      setState("on");
      return true;
    } finally {
      setBusy(false);
    }
  }, []);

  const disable = useCallback(async () => {
    setBusy(true);
    try {
      const token = readStorage(TOKEN_KEY);
      if (token) {
        await api.unregisterDevice(token).catch(() => undefined);
        const { getMessaging, deleteToken } = await import("firebase/messaging");
        await deleteToken(getMessaging(getFirebaseApp())).catch(() => undefined);
      }
      writeStorage(TOKEN_KEY, null);
      setState("off");
    } finally {
      setBusy(false);
    }
  }, []);

  return { state, busy, enable, disable, sendTest: api.testPush };
}
