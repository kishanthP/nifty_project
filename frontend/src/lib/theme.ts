import { useSyncExternalStore } from "react";

import { readStorage, writeStorage } from "./storage";

// Light or dark. Until the user clicks the toggle, the device's setting decides.
// index.html applies the saved choice before the page paints, so there's no flash.
export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const listeners = new Set<() => void>();

export function otherTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}

function currentTheme(): Theme {
  const saved = readStorage(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  writeStorage(STORAGE_KEY, theme);
  document.documentElement.dataset.theme = theme;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const media = window.matchMedia(DARK_QUERY);
  media.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", listener);
  };
}

/** The current theme (updates live). */
export function useTheme(): { theme: Theme; dark: boolean } {
  const theme = useSyncExternalStore(subscribe, currentTheme);
  return { theme, dark: theme === "dark" };
}
