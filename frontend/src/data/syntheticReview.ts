import type {
  EvidenceReference,
  MoneyValue,
  ObservableCheck,
  ReviewFinding,
  ReviewResult,
} from "../types";

const gbp = (amount: number): MoneyValue => ({ amount, currency: "GBP" });

const standardChecks = (status: ReviewFinding["status"]): ObservableCheck[] => {
  const hasSufficientEvidence = status !== "CANNOT_VERIFY" && status !== "UNSUPPORTED";
  return [
    {
      id: "investor-match",
      label: "Investor matched to the correct governing documents",
      state: hasSufficientEvidence ? "COMPLETE" : "UNRESOLVED",
    },
    {
      id: "effective-date",
      label: "Side-letter effective date checked",
      state: hasSufficientEvidence ? "COMPLETE" : "UNRESOLVED",
    },
    { id: "fee-base", label: "Fee base located", state: "COMPLETE" },
    {
      id: "recompute",
      label: "Fee calculation recomputed",
      state: hasSufficientEvidence ? "COMPLETE" : "UNRESOLVED",
    },
    {
      id: "compare",
      label: "Administrator value compared",
      state: !hasSufficientEvidence ? "UNRESOLVED" : status === "DISCREPANCY" ? "CONCERN" : "COMPLETE",
    },
  ];
};

const lpaEvidence: EvidenceReference = {
  id: "ev-lpa-fee",
  documentId: "doc-lpa",
  filename: "Example_Growth_Fund_III_LPA.pdf",
  documentRole: "LPA",
  sourceKind: "PDF",
  locator: "Section 8.1 · page 1",
  quote: "The default annual management fee is 2.0% of the applicable investor Fee Base.",
  context: "For Q3 2026 the quarterly fee is the annual rate multiplied by 0.25 and the Fee Base.",
};

function workbookEvidence(investorId: string, cell: string, value: number): EvidenceReference {
  return {
    id: `ev-${investorId.toLowerCase()}-workbook`,
    documentId: "doc-nav",
    filename: "Administrator_NAV_Q3_2026.xlsx",
    documentRole: "NAV_WORKBOOK",
    sourceKind: "SPREADSHEET",
    locator: `Investor Fees!${cell}`,
    value: new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 }).format(value),
    context: `${investorId} · Q3 management fee reported by the administrator`,
  };
}

function registerEvidence(investorId: string, feeBase: number): EvidenceReference {
  const row = Number(investorId.slice(2)) + 1;
  return {
    id: `ev-${investorId.toLowerCase()}-register`,
    documentId: "doc-register",
    filename: "investor_input_register.csv",
    documentRole: "INVESTOR_REGISTER",
    sourceKind: "CSV",
    locator: `row ${row} · fee_base`,
    value: formatPlainMoney(feeBase),
    context:
      `${investorId} · side_letter_expected = YES · ` +
      `side_letter_filename = ${investorId}_Side_Letter.pdf`,
  };
}

function sideLetterEvidence(
  investorId: string,
  section: string,
  rate: number,
  page: number,
  quote?: string,
  context?: string,
): EvidenceReference {
  return {
    id: `ev-${investorId.toLowerCase()}-side-letter`,
    documentId: `doc-${investorId.toLowerCase()}-side-letter`,
    filename: `${investorId}_Side_Letter.pdf`,
    documentRole: "SIDE_LETTER",
    sourceKind: "PDF",
    locator: `${section} · page ${page}`,
    quote: quote ?? `The annual management fee applicable to ${investorId} is ${rate.toFixed(2)}% of the Fee Base.`,
    context: context ?? "The term is effective during the Q3 2026 review period.",
  };
}

interface FindingInput {
  id: string;
  investorId: string;
  admin: number;
  expected?: number;
  base?: number;
  rate?: number;
  status: ReviewFinding["status"];
  cell: string;
  explanation: string;
  sideLetter?: { section: string; page: number; quote?: string; context?: string };
  concern?: string;
}

function createFinding(input: FindingInput): ReviewFinding {
  const hasExpectedValue = input.expected !== undefined;
  const evidence: EvidenceReference[] = [lpaEvidence];
  if (input.sideLetter && input.rate !== undefined) {
    evidence.push(
      sideLetterEvidence(
        input.investorId,
        input.sideLetter.section,
        input.rate,
        input.sideLetter.page,
        input.sideLetter.quote,
        input.sideLetter.context,
      ),
    );
  }
  if (input.base !== undefined) evidence.push(registerEvidence(input.investorId, input.base));
  evidence.push(workbookEvidence(input.investorId, input.cell, input.admin));

  return {
    id: input.id,
    investorId: input.investorId,
    checkName: "Management fee",
    administratorValue: gbp(input.admin),
    expectedValue: hasExpectedValue ? gbp(input.expected as number) : undefined,
    difference: hasExpectedValue ? gbp(Math.abs(input.admin - (input.expected as number))) : undefined,
    status: input.status,
    humanReviewState: "UNREVIEWED",
    explanation: input.explanation,
    calculation:
      input.base !== undefined && input.rate !== undefined && input.expected !== undefined
        ? {
            inputs: [
              { label: "Fee base", value: formatPlainMoney(input.base) },
              { label: "Applicable annual fee", value: `${input.rate}%` },
              { label: "Quarter factor", value: "0.25" },
            ],
            expression: `${formatPlainMoney(input.base)} × ${input.rate}% × 0.25`,
            result: gbp(input.expected),
          }
        : undefined,
    evidence,
    checksPerformed: standardChecks(input.status),
    challengerConcern: input.concern,
    verifierStatement: hasExpectedValue
      ? `Recalculation confirms an expected fee of ${formatPlainMoney(input.expected as number)}.`
      : "The expected fee cannot be recalculated without the investor-specific agreement.",
    requiredAction:
      input.status === "CANNOT_VERIFY"
        ? { label: `Upload ${input.investorId} side letter`, documentRole: "SIDE_LETTER" }
        : undefined,
    notes: [],
    versions: [
      {
        version: 1,
        createdAt: "2026-09-05T08:45:00.000Z",
        reason: "Initial deterministic review",
        applicableRate: input.rate,
        expectedValue: hasExpectedValue ? gbp(input.expected as number) : undefined,
      },
    ],
  };
}

function formatPlainMoney(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  }).format(value);
}

export const syntheticReviewFixture: ReviewResult = {
  id: "review-demo-q3-2026",
  version: 1,
  mode: "SYNTHETIC_DEMO",
  source: "DEVELOPMENT_FIXTURE",
  sourceNotice:
    "Development UI fixture aligned to the Atlas synthetic source pack — no backend review was performed.",
  fundName: "Example Growth Fund III",
  periodLabel: "Q3 2026 NAV review",
  createdAt: "2026-09-05T08:45:00.000Z",
  documents: [
    {
      id: "doc-nav",
      filename: "Administrator_NAV_Q3_2026.xlsx",
      role: "NAV_WORKBOOK",
      recognition: "RECOGNISED",
    },
    {
      id: "doc-lpa",
      filename: "Example_Growth_Fund_III_LPA.pdf",
      role: "LPA",
      recognition: "RECOGNISED",
    },
    ...["LP01", "LP02", "LP03", "LP04", "LP05"].map((investorId) => ({
      id: `doc-${investorId.toLowerCase()}-side-letter`,
      filename: `${investorId}_Side_Letter.pdf`,
      role: "SIDE_LETTER" as const,
      recognition: "RECOGNISED" as const,
    })),
    {
      id: "doc-register",
      filename: "investor_input_register.csv",
      role: "INVESTOR_REGISTER",
      recognition: "RECOGNISED",
    },
  ],
  findings: [
    createFinding({
      id: "finding-lp01-fee",
      investorId: "LP01",
      admin: 50_000,
      expected: 50_000,
      base: 10_000_000,
      rate: 2,
      status: "MATCH",
      cell: "F4",
      sideLetter: {
        section: "Section 3.1",
        page: 1,
        quote: "No management-fee variation is granted; the LPA default remains applicable.",
      },
      explanation: "The administrator applied the 2.0% annual LPA fee to LP01 for the quarter.",
    }),
    createFinding({
      id: "finding-lp02-fee",
      investorId: "LP02",
      admin: 37_500,
      expected: 37_500,
      base: 10_000_000,
      rate: 1.5,
      status: "MATCH",
      cell: "F5",
      sideLetter: { section: "Section 3.1", page: 1 },
      explanation: "The administrator applied LP02's effective 1.5% side-letter rate for the quarter.",
    }),
    createFinding({
      id: "finding-lp03-fee",
      investorId: "LP03",
      admin: 50_000,
      expected: 37_500,
      base: 10_000_000,
      rate: 1.5,
      status: "DISCREPANCY",
      cell: "F6",
      sideLetter: {
        section: "Section 3.1",
        page: 1,
      },
      explanation:
        "The administrator used the standard 2.0% fee from the LPA. LP03's effective side letter changes the applicable management fee to 1.5% for this period.",
      concern: "The administrator appears to use the LPA default instead of the investor-specific override.",
    }),
    createFinding({
      id: "finding-lp04-fee",
      investorId: "LP04",
      admin: 50_000,
      expected: 40_000,
      base: 8_000_000,
      rate: 2,
      status: "DISCREPANCY",
      cell: "F7",
      sideLetter: {
        section: "Section 3.1",
        page: 1,
        quote: "No management-fee rate variation is granted; the LPA default remains applicable.",
      },
      explanation:
        "The administrator applied the 2.0% LPA rate but used a £10,000,000 fee base. The investor register supports an £8,000,000 fee base for LP04.",
      concern: "The administrator workbook appears to use a fee base above the amount supported by the investor register.",
    }),
    createFinding({
      id: "finding-lp05-fee",
      investorId: "LP05",
      admin: 50_000,
      expected: 50_000,
      base: 10_000_000,
      rate: 2,
      status: "MATCH",
      cell: "F8",
      sideLetter: {
        section: "Section 3.1",
        page: 1,
        quote: "The annual management fee applicable to LP05 is 1.5% of the Fee Base.",
        context: "Effective from 1 October 2026, after the Q3 2026 review period.",
      },
      explanation: "LP05's 1.5% side-letter rate starts after Q3 2026, so the administrator correctly applied the 2.0% LPA rate for this period.",
    }),
    createFinding({
      id: "finding-lp06-fee",
      investorId: "LP06",
      admin: 37_500,
      base: 10_000_000,
      status: "CANNOT_VERIFY",
      cell: "F9",
      explanation:
        "The investor register indicates that LP06 has a side letter, but no matching side-letter document was provided.",
      concern: "An expected investor agreement is missing, so the applicable fee term cannot be established.",
    }),
  ],
  outputCapabilities: {
    pdf: false,
    excel: false,
    json: true,
    emailPrepare: true,
    emailSend: false,
  },
};
