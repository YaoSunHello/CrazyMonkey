import { render, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import { syntheticReviewFixture } from "../data/syntheticReview";
import { FindingDetail } from "./FindingDetail";

describe("FindingDetail exact values and audit history", () => {
  it("renders exact string money and does not present current terms as historical values", () => {
    const finding = structuredClone(syntheticReviewFixture.findings.find((item) => item.investorId === "LP03")!);
    finding.administratorValue = { amount: "90071992547409.01", currency: "GBP" };
    finding.expectedValue = { amount: "90071992547400.00", currency: "GBP" };
    finding.difference = { amount: "9.01", currency: "GBP" };
    if (finding.calculation) {
      finding.calculation.result = structuredClone(finding.expectedValue);
    }
    finding.versions = [
      {
        version: 1,
        createdAt: "2026-09-05T12:00:00Z",
        reason: "Initial source-linked deterministic review",
        applicableRate: "1.5000",
        expectedValue: structuredClone(finding.expectedValue),
      },
      {
        version: 2,
        createdAt: "2026-09-05T13:00:00Z",
        reason: "Human review: Reviewed",
        applicableRate: "1.5000",
        expectedValue: structuredClone(finding.expectedValue),
      },
    ];

    render(
      <FindingDetail
        finding={finding}
        reviewContext={{ fundName: "Exact Fund", periodLabel: "Q3 2026", mode: "LIVE_OFFLINE", version: 2 }}
        saving={false}
        onBack={vi.fn()}
        onOpenEvidence={vi.fn()}
        onHumanReview={vi.fn(async () => undefined)}
        onCorrectTerm={vi.fn(async () => undefined)}
        onUploadDocument={vi.fn(async () => undefined)}
        canUploadDocument={false}
        canCorrectTerm={false}
      />,
    );

    expect(screen.getByText("£90,071,992,547,409.01")).toBeInTheDocument();
    expect(screen.getByText("£9.01 above reconstruction")).toBeInTheDocument();

    const history = screen.getByRole("region", { name: "Review versions" });
    expect(within(history).getByText("Current reconstructed terms")).toBeInTheDocument();
    expect(within(history).getByText("£90,071,992,547,400 expected")).toBeInTheDocument();
    expect(within(history).getByText("1.5% annual fee")).toBeInTheDocument();
    expect(within(history).getByText(/not claimed as values for earlier audit events/i)).toBeInTheDocument();
    expect(within(history).getByText("Initial source-linked deterministic review")).toBeInTheDocument();
    expect(within(history).getByText("Human review: Reviewed")).toBeInTheDocument();
    expect(within(history).getAllByText(/^Recorded /)).toHaveLength(2);
    expect(within(history).queryByText("Previous version")).not.toBeInTheDocument();
    expect(within(history).getByText("Version 1").closest("article")).not.toHaveTextContent("£");
  });
});
