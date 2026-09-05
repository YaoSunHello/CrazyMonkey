import { formatMoney } from "./format";

describe("formatMoney", () => {
  it("keeps whole-pound review values compact", () => {
    expect(formatMoney({ amount: 12_500, currency: "GBP" })).toBe("£12,500");
  });

  it("preserves non-zero minor units", () => {
    expect(formatMoney({ amount: 1_234.5, currency: "GBP" })).toBe("£1,234.50");
    expect(formatMoney({ amount: 0.07, currency: "GBP" })).toBe("£0.07");
  });

  it("renders canonical decimal strings beyond JavaScript's safe integer range without rounding", () => {
    expect(formatMoney({ amount: "90071992547409.01", currency: "GBP" })).toBe(
      "£90,071,992,547,409.01",
    );
  });

  it("preserves meaningful precision instead of silently rounding to pennies", () => {
    expect(formatMoney({ amount: "1234.567800", currency: "GBP" })).toBe("£1,234.5678");
  });

  it("uses an em dash when no monetary value is available", () => {
    expect(formatMoney()).toBe("—");
  });
});
