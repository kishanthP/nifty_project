import { useSyncExternalStore } from "react";

import { readStorage, writeStorage } from "./storage";

// "system" follows the OS setting; light/dark are the user's override.
// index.html applies the saved choice before the page paints, so there's no flash.
export type ThemeChoice = "system" | "light" | "dark";

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const ORDER: ThemeChoice[] = ["system", "light", "dark"];
const listeners = new Set<() => void>();

export function nextTheme(choice: ThemeChoice): ThemeChoice {
  return ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
}

function readChoice(): ThemeChoice {
  const saved = readStorage(STORAGE_KEY);
  return saved === "light" || saved === "dark" ? saved : "system";
}

export function setThemeChoice(choice: ThemeChoice): void {
  writeStorage(STORAGE_KEY, choice === "system" ? null : choice);
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
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

// A primitive snapshot so React only re-renders when something actually changed.
function snapshot(): string {
  const choice = readChoice();
  const dark = choice === "dark" || (choice === "system" && window.matchMedia(DARK_QUERY).matches);
  return `${choice}:${dark ? 1 : 0}`;
}

/** The chosen theme and whether the page is dark right now (updates live). */
export function useTheme(): { choice: ThemeChoice; dark: boolean } {
  const [choice, dark] = useSyncExternalStore(subscribe, snapshot).split(":");
  return { choice: choice as ThemeChoice, dark: dark === "1" };
}
