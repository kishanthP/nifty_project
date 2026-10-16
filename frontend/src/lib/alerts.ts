import type { AlertCondition } from "../types/api";
import { formatPrice } from "./format";

/** Price above the current one → "above"; below → "below"; equal or invalid → null. */
export function inferCondition(target: number, current: number): AlertCondition | null {
  if (!Number.isFinite(target) || target <= 0 || !Number.isFinite(current)) return null;
  if (target > current) return "above";
  if (target < current) return "below";
  return null;
}

/** Would this alert fire right away? (Same rule as the backend.) */
export function isConditionMet(condition: AlertCondition, target: number, current: number): boolean {
  return condition === "above" ? current >= target : current <= target;
}

/** Round to 2 decimals, e.g. for quick-pick buttons. */
export function roundPrice(value: number): number {
  return Math.round(value * 100) / 100;
}

/** "10.00 to go" — how far the price must move before the alert fires. */
export function distanceToTarget(condition: AlertCondition, target: number, current: number): number {
  return condition === "above" ? target - current : current - target;
}

export function describeAlert(name: string, condition: AlertCondition, target: number): string {
  return `Notify me when ${name} goes ${condition} ₹${formatPrice(target)}`;
}

/**
 * Check a "High & low" pair against the current price (same rules as the backend).
 * Returns a message to show, or null when the pair is valid.
 */
export function rangeProblem(name: string, high: number, low: number, current: number | null): string | null {
  if (high <= low) return "The high price must be above the low price.";
  if (current == null) return null;
  if (current >= high) return `${name} is already at or above ₹${formatPrice(high)}. Choose a higher high price.`;
  if (current <= low) return `${name} is already at or below ₹${formatPrice(low)}. Choose a lower low price.`;
  return null;
}

export function describeRange(name: string, high: number, low: number): string {
  return `Notify me when ${name} goes above ₹${formatPrice(high)} or below ₹${formatPrice(low)}`;
}

/** True when the target is unusually far from the current price (likely a typo). */
export function isFarFromPrice(target: number, current: number, maxFraction = 0.1): boolean {
  return current > 0 && Math.abs(target - current) / current > maxFraction;
}

/** Parse what the user typed: allows "22,560.5"; returns NaN when invalid or > 2 decimals. */
export function parsePriceInput(raw: string): number {
  const cleaned = raw.replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return Number.NaN;
  return Number(cleaned);
}
