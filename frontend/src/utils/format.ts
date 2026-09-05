import type { DecimalValue, DocumentRole, FindingStatus, HumanReviewState, MoneyValue } from "../types";
import { canonicalDecimalText } from "./decimal";

export const documentRoleLabels: Record<DocumentRole, string> = {
  NAV_WORKBOOK: "NAV workbook",
  LPA: "LPA",
  SIDE_LETTER: "Side letter",
  INVESTOR_REGISTER: "Investor register",
  SUPPORTING: "Other supporting file",
};

export const findingStatusLabels: Record<FindingStatus, string> = {
  MATCH: "Match",
  DISCREPANCY: "Discrepancy",
  CANNOT_VERIFY: "Cannot verify",
  UNSUPPORTED: "Unsupported",
};

export const humanReviewLabels: Record<HumanReviewState, string> = {
  UNREVIEWED: "Unreviewed",
  REVIEWED: "Reviewed",
  NEEDS_FOLLOW_UP: "Needs follow-up",
  TERM_CONFIRMED: "Term confirmed",
};

export function formatMoney(value?: MoneyValue): string {
  if (!value) return "—";
  const decimal = displayDecimalParts(value.amount, 2);
  const affixes = currencyAffixes(value.currency);
  return `${decimal.negative ? "-" : ""}${affixes.prefix}${decimal.number}${affixes.suffix}`;
}

export function formatDecimal(value: DecimalValue): string {
  const decimal = displayDecimalParts(value, 0);
  return `${decimal.negative ? "-" : ""}${decimal.number}`;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function statusPriority(status: FindingStatus): number {
  return { DISCREPANCY: 0, CANNOT_VERIFY: 1, UNSUPPORTED: 2, MATCH: 3 }[status];
}

function displayDecimalParts(value: DecimalValue, fractionalMinimum: number) {
  const canonical = canonicalDecimalText(value);
  const negative = canonical.startsWith("-");
  const unsigned = negative ? canonical.slice(1) : canonical;
  const [integer, rawFraction = ""] = unsigned.split(".");
  const significantFraction = rawFraction.replace(/0+$/, "");
  const fraction = significantFraction.length > 0
    ? significantFraction.padEnd(fractionalMinimum, "0")
    : "";
  const groupedInteger = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return {
    negative: negative && !/^0(?:\.0+)?$/.test(unsigned),
    number: `${groupedInteger}${fraction ? `.${fraction}` : ""}`,
  };
}

function currencyAffixes(currency: string): { prefix: string; suffix: string } {
  try {
    const parts = new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).formatToParts(0);
    const numeric = new Set(["integer", "group", "decimal", "fraction"]);
    const firstNumeric = parts.findIndex((part) => numeric.has(part.type));
    let lastNumeric = firstNumeric;
    parts.forEach((part, index) => {
      if (numeric.has(part.type)) lastNumeric = index;
    });
    return {
      prefix: parts.slice(0, firstNumeric).map((part) => part.value).join(""),
      suffix: parts.slice(lastNumeric + 1).map((part) => part.value).join(""),
    };
  } catch {
    return { prefix: `${currency} `, suffix: "" };
  }
}
