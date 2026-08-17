import { navigationFromHash } from "./AdminShell";

describe("admin deep links", () => {
  it("opens model settings from the fixed settings hash", () => {
    expect(navigationFromHash("#settings")).toBe("settings");
    expect(navigationFromHash("#/settings")).toBe("settings");
  });

  it("opens plugin management from the fixed plugins hash", () => {
    expect(navigationFromHash("#plugins")).toBe("plugins");
    expect(navigationFromHash("#/plugins")).toBe("plugins");
  });

  it("falls back to the overview for unknown hashes", () => {
    expect(navigationFromHash("#unknown" as string)).toBe("overview");
    expect(navigationFromHash("")).toBe("overview");
  });
});
