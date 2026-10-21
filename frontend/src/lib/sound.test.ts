import { describe, expect, it } from "vitest";

import { soundPattern } from "./sound";

describe("soundPattern", () => {
  it("rings twice for a price-up (above) alert", () => {
    expect(soundPattern("above")).toHaveLength(2);
  });

  it("rings four times, lower, for a price-down (below) alert", () => {
    const down = soundPattern("below");
    expect(down).toHaveLength(4);
    expect(down[0].frequency).toBeLessThan(soundPattern("above")[0].frequency);
  });

  it("spaces the tings evenly", () => {
    const times = soundPattern("below").map((t) => t.at);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(new Set(times).size).toBe(4);
  });
});
