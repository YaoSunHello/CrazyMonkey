import type { DocumentRole, FindingStatus, HumanReviewState, MoneyValue } from "../types";

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
  const amountInMinorUnits = Math.round(Math.abs(value.amount) * 100);
  const hasMinorUnits = amountInMinorUnits % 100 !== 0;
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: value.currency,
    minimumFractionDigits: hasMinorUnits ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value.amount);
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
