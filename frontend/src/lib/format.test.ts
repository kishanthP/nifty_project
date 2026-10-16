import { describe, expect, it } from "vitest";

import { formatPercent, formatPrice, formatSigned, timeAgo } from "./format";

describe("formatPrice", () => {
  it("uses Indian digit grouping", () => {
    expect(formatPrice(22563.4)).toBe("22,563.40");
    expect(formatPrice(1234567)).toBe("12,34,567.00");
  });

  it("shows a dash for missing values", () => {
    expect(formatPrice(null)).toBe("—");
  });
});

describe("signed values", () => {
  it("adds + and − signs", () => {
    expect(formatSigned(13.4)).toBe("+13.40");
    expect(formatSigned(-5)).toBe("−5.00");
    expect(formatPercent(0.0594)).toBe("+0.06%");
    expect(formatPercent(-1.234)).toBe("−1.23%");
  });
});

describe("timeAgo", () => {
  it("describes recent times", () => {
    const now = Date.parse("2026-10-15T10:00:00Z");
    expect(timeAgo("2026-10-15T09:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-10-15T09:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-10-15T09:55:00Z", now)).toBe("5m ago");
  });
});
