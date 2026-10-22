import { describe, expect, it } from "vitest";

import {
  checkRows,
  describeBatch,
  describeRange,
  distanceToTarget,
  inferCondition,
  isConditionMet,
  isFarFromPrice,
  parsePriceInput,
  rangeProblem,
} from "./alerts";

describe("rangeProblem (High & low)", () => {
  it("accepts the user's example: 22,560 / 22,540 around 22,550", () => {
    expect(rangeProblem("NIFTY 50", 22560, 22540, 22550)).toBeNull();
    expect(describeRange("NIFTY 50", 22560, 22540)).toBe(
      "Notify me when NIFTY 50 goes above ₹22,560.00 or below ₹22,540.00",
    );
  });

  it("rejects pairs that are inverted or already hit", () => {
    expect(rangeProblem("NIFTY 50", 22540, 22560, 22550)).toMatch(/high price must be above/);
    expect(rangeProblem("NIFTY 50", 22550, 22500, 22550)).toMatch(/already at or above/);
    expect(rangeProblem("NIFTY 50", 22600, 22550, 22550)).toMatch(/already at or below/);
  });

  it("only checks the order when there's no live price", () => {
    expect(rangeProblem("NIFTY 50", 22560, 22540, null)).toBeNull();
  });
});

describe("isFarFromPrice", () => {
  it("flags likely typos but not normal targets", () => {
    expect(isFarFromPrice(22560, 22550)).toBe(false);
    expect(isFarFromPrice(2251822513, 22550)).toBe(true);
    expect(isFarFromPrice(2255, 22550)).toBe(true);
  });
});

describe("inferCondition", () => {
  it("picks 'above' for a higher target (22550 → 22560)", () => {
    expect(inferCondition(22560, 22550)).toBe("above");
  });

  it("picks 'below' for a lower target (22550 → 22540)", () => {
    expect(inferCondition(22540, 22550)).toBe("below");
  });

  it("returns null for the current price or invalid input", () => {
    expect(inferCondition(22550, 22550)).toBeNull();
    expect(inferCondition(Number.NaN, 22550)).toBeNull();
    expect(inferCondition(-5, 22550)).toBeNull();
  });
});

describe("isConditionMet", () => {
  it("matches the backend rule (>= for above, <= for below)", () => {
    expect(isConditionMet("above", 22560, 22560)).toBe(true);
    expect(isConditionMet("above", 22560, 22559.95)).toBe(false);
    expect(isConditionMet("below", 22540, 22540)).toBe(true);
    expect(isConditionMet("below", 22540, 22540.05)).toBe(false);
  });
});

describe("distanceToTarget", () => {
  it("is positive while the alert is still pending", () => {
    expect(distanceToTarget("above", 22560, 22550)).toBe(10);
    expect(distanceToTarget("below", 22540, 22550)).toBe(10);
  });
});

describe("parsePriceInput", () => {
  it("accepts plain and comma-grouped prices", () => {
    expect(parsePriceInput("22560")).toBe(22560);
    expect(parsePriceInput("22,560.5")).toBe(22560.5);
  });

  it("rejects junk and more than 2 decimals", () => {
    expect(parsePriceInput("abc")).toBeNaN();
    expect(parsePriceInput("22560.123")).toBeNaN();
    expect(parsePriceInput("")).toBeNaN();
  });
});

describe("checkRows (Multiple)", () => {
  const row = (input: string, manualCondition: "above" | "below" | null = null) => ({ input, manualCondition });

  it("accepts the user's example: 22,310 and 22,320 above 22,300", () => {
    const checked = checkRows([row("22310"), row("22320")], 22300);
    expect(checked.map((r) => [r.condition, r.error])).toEqual([
      ["above", null],
      ["above", null],
    ]);
    expect(describeBatch([{ condition: "above", price: 22310 }, { condition: "below", price: 22290 }])).toBe(
      "above ₹22,310.00, below ₹22,290.00",
    );
  });

  it("skips empty rows and flags invalid, duplicate and already-met prices", () => {
    const [empty, invalid, first, duplicate, met, current] = checkRows(
      [row(""), row("abc"), row("22310"), row("22,310"), row("22290", "above"), row("22300")],
      22300,
    );
    expect(empty).toMatchObject({ empty: true, error: null });
    expect(invalid.error).toMatch(/Enter a price/);
    expect(first.error).toBeNull();
    expect(duplicate.error).toMatch(/already in the list/);
    expect(met.error).toMatch(/Already at or above/);
    expect(current.error).toMatch(/current price/);
  });

  it("lets the user flip the direction", () => {
    const [down] = checkRows([row("22320", "below")], 22300);
    expect(down.condition).toBe("below");
    expect(down.error).toMatch(/at or below/);
  });
});
