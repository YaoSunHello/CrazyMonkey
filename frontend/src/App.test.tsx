import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { MockReviewAdapter } from "./api/mockReviewAdapter";
import type { ReviewProgress, ReviewResult } from "./types";

class ImmediateMockReviewAdapter extends MockReviewAdapter {
  override async getProgress(reviewId: string): Promise<ReviewProgress> {
    return {
      reviewId,
      state: "COMPLETE",
      stages: [],
      messages: [],
    };
  }
}

class BelowExpectedMockReviewAdapter extends ImmediateMockReviewAdapter {
  override async getReview(reviewId: string): Promise<ReviewResult> {
    const review = await super.getReview(reviewId);
    const finding = review.findings.find((item) => item.investorId === "LP03")!;
    finding.administratorValue = { amount: 37_500, currency: "GBP" };
    finding.expectedValue = { amount: 50_000, currency: "GBP" };
    finding.difference = { amount: -12_500, currency: "GBP" };
    if (finding.calculation) finding.calculation.result = { amount: 50_000, currency: "GBP" };
    return review;
  }
}

describe("CrazyMonkey review workflow", () => {
  it("renders the synthetic review totals and keeps human review separate from the finding status", async () => {
    const user = userEvent.setup();
    render(<App adapter={new ImmediateMockReviewAdapter()} />);

    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));

    expect(await screen.findByRole("heading", { name: "Review summary" })).toBeInTheDocument();
    expect(screen.getByText("Development UI fixture aligned to the Atlas synthetic source pack — no backend review was performed.")).toBeInTheDocument();
    const totals = within(screen.getByRole("region", { name: "Review totals" }));
    expect(within(totals.getByText("Total checks").closest("article")!).getByText("6")).toBeInTheDocument();
    expect(within(totals.getByText(/Matches/).closest("article")!).getByText("3")).toBeInTheDocument();
    expect(within(totals.getByText(/Discrepancies/).closest("article")!).getByText("2")).toBeInTheDocument();
    expect(within(totals.getByText(/Cannot verify/).closest("article")!).getByText("1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Review next exception" }));
    expect(await screen.findByRole("heading", { name: /LP03.*Management fee/ })).toBeInTheDocument();
    expect(screen.getByText("Cedar Grove Foundation", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText("Discrepancy").length).toBeGreaterThan(0);
    expect(screen.getByText("£12,500 above reconstruction")).toBeInTheDocument();
    expect(screen.getByText("Not assigned")).toBeInTheDocument();
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Exact arithmetic and rule checks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence-linked challenge for the reviewer" })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Reviewer display name/), "Test reviewer");
    await user.click(screen.getByRole("button", { name: "Mark reviewed" }));

    await waitFor(() => expect(screen.getAllByText("Reviewed").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Discrepancy").length).toBeGreaterThan(0);
    expect(screen.getByText("This state is separate from the computational finding.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to findings" }));
    await user.click(await screen.findByRole("button", { name: /Human-reviewed\s*1/i }));

    const reviewedRow = screen.getByRole("row", { name: /LP03.*Management fee/ });
    expect(within(reviewedRow).getByText("Discrepancy")).toBeInTheDocument();
    expect(within(reviewedRow).getByText("Reviewed")).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /LP04.*Management fee/ })).not.toBeInTheDocument();
  });

  it("does not imply uploaded packs can be reviewed in development fixture mode", async () => {
    const user = userEvent.setup();
    const adapter = new MockReviewAdapter();
    render(<App adapter={adapter} />);

    const input = screen.getByLabelText("Select files") as HTMLInputElement;
    await user.upload(input, [
      new File(["workbook"], "Administrator_NAV_Q3_2026.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      new File(["lpa"], "Example_Growth_Fund_III_LPA.pdf", { type: "application/pdf" }),
      new File(["register"], "investor_input_register.csv", { type: "text/csv" }),
    ]);

    expect(await screen.findByText("Administrator_NAV_Q3_2026.xlsx")).toBeInTheDocument();
    expect(screen.getByText("Example_Growth_Fund_III_LPA.pdf")).toBeInTheDocument();
    expect(screen.getByText("investor_input_register.csv")).toBeInTheDocument();
    expect(screen.getByText("Development fixture mode")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start review/ })).toBeDisabled();
    expect(screen.getByText(/Uploaded-pack review is disabled/i)).toHaveTextContent(/Atlas is not connected/i);

    await expect(adapter.startReview([])).rejects.toThrow(
      "Uploaded-pack review requires the Atlas service. Development fixture mode will not invent findings for selected files.",
    );
  });

  it("shows a signed negative difference as an absolute magnitude below reconstruction", async () => {
    const user = userEvent.setup();
    render(<App adapter={new BelowExpectedMockReviewAdapter()} />);

    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review next exception" }));

    expect(await screen.findByText("£12,500 below reconstruction")).toBeInTheDocument();
    expect(screen.queryByText("-£12,500 below reconstruction")).not.toBeInTheDocument();
  });
});
