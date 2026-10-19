import { describe, expect, it } from "vitest";

import { soundPattern } from "./sound";

describe("soundPattern", () => {
  it("rings once for a high-price (above) alert", () => {
    expect(soundPattern("above")).toHaveLength(1);
  });

  it("rings twice, lower, for a low-price (below) alert", () => {
    const low = soundPattern("below");
    expect(low).toHaveLength(2);
    expect(low[1].at).toBeGreaterThan(low[0].at);
    expect(low[0].frequency).toBeLessThan(soundPattern("above")[0].frequency);
  });
});
