import { describe, expect, it } from "vitest";

import { otherTheme } from "./theme";

describe("otherTheme", () => {
  it("toggles between light and dark", () => {
    expect(otherTheme("light")).toBe("dark");
    expect(otherTheme("dark")).toBe("light");
  });
});
