import { useSyncExternalStore } from "react";

import type { AlertCondition } from "../types/api";
import { readStorage, writeStorage } from "./storage";

// Alert sounds, made with the Web Audio API (no sound files):
//   above (price up)   -> "ting ting"            two bright bell tones
//   below (price down) -> "ting ting ting ting"  four lower bell tones
//
// Browsers only allow sound after the user has interacted with the page, so the
// audio engine is unlocked on the first click / tap / key press.

export interface Ting {
  frequency: number; // Hz
  at: number; // seconds after the start
}

const TING_GAP_SECONDS = 0.22;

export function soundPattern(condition: AlertCondition): Ting[] {
  const [frequency, count] = condition === "above" ? [1568, 2] : [1175, 4]; // G6 / D6
  return Array.from({ length: count }, (_, i) => ({ frequency, at: i * TING_GAP_SECONDS }));
}

const STORAGE_KEY = "sound";
const listeners = new Set<() => void>();
let context: AudioContext | null = null;

function getContext(): AudioContext | null {
  if (!context && typeof AudioContext !== "undefined") context = new AudioContext();
  return context;
}

/** Call once at startup: unlocks audio on the first user interaction. */
export function unlockAudioOnFirstGesture(): void {
  const unlock = () => {
    void getContext()?.resume();
    for (const name of ["pointerdown", "keydown", "touchstart"]) {
      window.removeEventListener(name, unlock);
    }
  };
  for (const name of ["pointerdown", "keydown", "touchstart"]) {
    window.addEventListener(name, unlock, { passive: true });
  }
}

function playTing(ctx: AudioContext, { frequency, at }: Ting): void {
  const start = ctx.currentTime + at;
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.3, start + 0.005);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + 1.1);
  gain.connect(ctx.destination);
  // A bell = the main tone plus a quieter, faster-fading overtone.
  for (const [ratio, level] of [
    [1, 1],
    [2.76, 0.25],
  ]) {
    const partial = ctx.createGain();
    partial.gain.value = level;
    partial.connect(gain);
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = frequency * ratio;
    osc.connect(partial);
    osc.start(start);
    osc.stop(start + 1.15);
  }
}

const recentlyPlayed = new Map<string, number>();

/** Plays the alert's sound (once per alert, if sound is on and audio is unlocked). */
export function playAlertSound(condition: AlertCondition, alertId?: string): void {
  if (!isSoundOn()) return;
  if (alertId) {
    const now = Date.now();
    if (now - (recentlyPlayed.get(alertId) ?? 0) < 10_000) return;
    recentlyPlayed.set(alertId, now);
  }
  const ctx = getContext();
  if (!ctx) return;
  void ctx.resume().then(() => {
    for (const ting of soundPattern(condition)) playTing(ctx, ting);
  });
}

// --- on/off setting (default on), remembered per browser ---
export function isSoundOn(): boolean {
  return readStorage(STORAGE_KEY) !== "off";
}

export function setSoundOn(on: boolean): void {
  writeStorage(STORAGE_KEY, on ? null : "off");
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useSoundOn(): boolean {
  return useSyncExternalStore(subscribe, isSoundOn);
}
