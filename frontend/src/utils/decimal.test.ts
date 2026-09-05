import {
  absoluteMoneyValue,
  compareDecimalValues,
  isCanonicalDecimalString,
  isZeroDecimalValue,
} from "./decimal";

describe("exact decimal helpers", () => {
  it("compares high-precision values without converting them to JavaScript numbers", () => {
    expect(compareDecimalValues("90071992547409.01", "90071992547409.00")).toBe(1);
    expect(compareDecimalValues("-90071992547409.01", "-90071992547409.00")).toBe(-1);
    expect(compareDecimalValues("1.2300", 1.23)).toBe(0);
  });

  it("detects signed decimal zero and returns an exact absolute money value", () => {
    expect(isZeroDecimalValue("-0.0000")).toBe(true);
    expect(absoluteMoneyValue({ amount: "-90071992547409.01", currency: "GBP" })).toEqual({
      amount: "90071992547409.01",
      currency: "GBP",
    });
  });

  it("accepts only plain canonical decimal strings", () => {
    expect(isCanonicalDecimalString("90071992547409.01")).toBe(true);
    expect(isCanonicalDecimalString("1e3")).toBe(false);
    expect(isCanonicalDecimalString("01.00")).toBe(false);
    expect(isCanonicalDecimalString(" 1.00 ")).toBe(false);
  });
});
