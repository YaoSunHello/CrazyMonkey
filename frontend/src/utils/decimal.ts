import type { DecimalValue, MoneyValue } from "../types";

const canonicalDecimalPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

interface DecimalParts {
  negative: boolean;
  integer: string;
  fraction: string;
}

export function isCanonicalDecimalString(value: string): boolean {
  return canonicalDecimalPattern.test(value);
}

export function canonicalDecimalText(value: DecimalValue): string {
  if (typeof value === "string") {
    if (!isCanonicalDecimalString(value)) {
      throw new Error("Expected a canonical decimal string.");
    }
    return value;
  }
  if (!Number.isFinite(value)) {
    throw new Error("Expected a finite decimal value.");
  }
  if (Object.is(value, -0)) return "0";
  return expandExponent(String(value));
}

export function compareDecimalValues(left: DecimalValue, right: DecimalValue): -1 | 0 | 1 {
  const leftParts = normalizedParts(left);
  const rightParts = normalizedParts(right);
  if (leftParts.negative !== rightParts.negative) return leftParts.negative ? -1 : 1;

  const magnitude = compareMagnitude(leftParts, rightParts);
  if (magnitude === 0) return 0;
  return leftParts.negative ? (magnitude === 1 ? -1 : 1) : magnitude;
}

export function isZeroDecimalValue(value: DecimalValue): boolean {
  const parts = normalizedParts(value);
  return parts.integer === "0" && parts.fraction.length === 0;
}

export function absoluteMoneyValue(value: MoneyValue): MoneyValue {
  const text = canonicalDecimalText(value.amount);
  return { ...value, amount: text.startsWith("-") ? text.slice(1) : text };
}

function normalizedParts(value: DecimalValue): DecimalParts {
  const text = canonicalDecimalText(value);
  const negative = text.startsWith("-");
  const unsigned = negative ? text.slice(1) : text;
  const [rawInteger, rawFraction = ""] = unsigned.split(".");
  const integer = rawInteger.replace(/^0+(?=\d)/, "");
  const fraction = rawFraction.replace(/0+$/, "");
  const isZero = integer === "0" && fraction.length === 0;
  return { negative: negative && !isZero, integer, fraction };
}

function compareMagnitude(left: DecimalParts, right: DecimalParts): -1 | 0 | 1 {
  if (left.integer.length !== right.integer.length) {
    return left.integer.length < right.integer.length ? -1 : 1;
  }
  if (left.integer !== right.integer) return left.integer < right.integer ? -1 : 1;

  const width = Math.max(left.fraction.length, right.fraction.length);
  const leftFraction = left.fraction.padEnd(width, "0");
  const rightFraction = right.fraction.padEnd(width, "0");
  if (leftFraction === rightFraction) return 0;
  return leftFraction < rightFraction ? -1 : 1;
}

function expandExponent(value: string): string {
  if (!/[eE]/.test(value)) return value;
  const match = /^(-?)(\d+)(?:\.(\d*))?[eE]([+-]?\d+)$/.exec(value);
  if (!match) throw new Error("Expected a finite decimal value.");

  const [, sign, integer, fraction = "", exponentText] = match;
  const digits = `${integer}${fraction}`;
  const decimalIndex = integer.length + Number(exponentText);
  if (decimalIndex <= 0) return `${sign}0.${"0".repeat(-decimalIndex)}${digits}`;
  if (decimalIndex >= digits.length) return `${sign}${digits}${"0".repeat(decimalIndex - digits.length)}`;
  return `${sign}${digits.slice(0, decimalIndex)}.${digits.slice(decimalIndex)}`;
}
