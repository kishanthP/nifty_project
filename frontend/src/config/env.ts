const env = import.meta.env;

export const config = {
  apiUrl: (env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, ""),
  authDevMode: env.VITE_AUTH_DEV_MODE === "true",
  firebase: {
    apiKey: env.VITE_FIREBASE_API_KEY ?? "",
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN ?? "",
    projectId: env.VITE_FIREBASE_PROJECT_ID ?? "",
    storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET ?? "",
    messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID ?? "",
    appId: env.VITE_FIREBASE_APP_ID ?? "",
  },
  vapidKey: env.VITE_FIREBASE_VAPID_KEY ?? "",
};

export const isFirebaseConfigured = Boolean(
  config.firebase.apiKey && config.firebase.projectId && config.firebase.appId,
);

export const isPushConfigured =
  isFirebaseConfigured && Boolean(config.vapidKey && config.firebase.messagingSenderId);

export const wsUrl = `${config.apiUrl.replace(/^http/, "ws")}/api/v1/ws/market`;

export const DEFAULT_SYMBOL = "NIFTY50";
