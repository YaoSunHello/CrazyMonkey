import { formatMoney } from "./format";

describe("formatMoney", () => {
  it("keeps whole-pound review values compact", () => {
    expect(formatMoney({ amount: 12_500, currency: "GBP" })).toBe("£12,500");
  });

  it("preserves non-zero minor units", () => {
    expect(formatMoney({ amount: 1_234.5, currency: "GBP" })).toBe("£1,234.50");
    expect(formatMoney({ amount: 0.07, currency: "GBP" })).toBe("£0.07");
  });

  it("uses an em dash when no monetary value is available", () => {
    expect(formatMoney()).toBe("—");
  });
});
