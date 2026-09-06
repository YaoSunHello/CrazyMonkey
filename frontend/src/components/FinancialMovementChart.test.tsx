import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FinancialMovementChart } from "./FinancialMovementChart";
import { resultWithCsvFixture, transactionCsvFixture } from "../test/transactionCsvFixtures";
import type { JobResult } from "../workspaceTypes";

function panel(result = resultWithCsvFixture, text = transactionCsvFixture(result)) {
  const fetchCsv = vi.fn(async () => text);
  const onSelectFinding = vi.fn();
  const props = { result, document: result.documents[0], fetchCsv, downloadUrl: "/api/ui/v1/jobs/job-123/transactions.csv", onSelectFinding };
  return { ...render(<FinancialMovementChart {...props} />), props, fetchCsv, onSelectFinding };
}

function kpi(label: string) { return screen.getByText(label).closest("div")!; }

describe("FinancialMovementChart", () => {
  it("loads the actual CSV independently and exposes exact totals, provenance, download and source findings", async () => {
    const user = userEvent.setup();
    const { fetchCsv, onSelectFinding } = panel(resultWithCsvFixture, transactionCsvFixture(resultWithCsvFixture, {
      "row-older": { debit: "-0.44", signed_movement: "-0.44" },
    }));
    expect(screen.getByRole("status")).toHaveTextContent("Loading the generated transaction CSV");
    await screen.findByRole("img", { name: /Recorded balance and signed movements in GBP/ });
    expect(fetchCsv).toHaveBeenCalledWith(
      "job-123",
      resultWithCsvFixture.exports!.transactions_csv!.sha256,
      expect.any(AbortSignal),
    );
    expect(kpi("Money in")).toHaveTextContent("125.00 GBP");
    expect(kpi("Money out")).toHaveTextContent("0.44 GBP");
    expect(kpi("Net movement")).toHaveTextContent("124.56 GBP");
    expect(screen.getByText(/2 source rows · 0 balance links pass · 1 fail · 1 not checked/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download transaction CSV" })).toHaveAttribute("href", "/api/ui/v1/jobs/job-123/transactions.csv");
    expect(screen.getByRole("link", { name: "Download transaction CSV" })).toHaveAttribute("download", "job-123-transactions.csv");
    expect(screen.getByTitle(resultWithCsvFixture.exports!.transactions_csv!.sha256)).toHaveTextContent("abcdef123456");
    await user.click(screen.getByText(/View exact transaction values/));
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("−0.44")).toHaveLength(2);
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Earlier balance");
    expect(rows[2]).toHaveTextContent("Investor subscription");
    await user.click(screen.getByRole("button", { name: "Inspect FAIL · row 1" }));
    expect(onSelectFinding).toHaveBeenCalledWith("finding-link-1");
  });

  it("retries a failed CSV request without any mock chart or financial totals", async () => {
    const user = userEvent.setup();
    const fetchCsv = vi.fn().mockRejectedValueOnce(new Error("Network unavailable")).mockResolvedValue(transactionCsvFixture());
    render(<FinancialMovementChart result={resultWithCsvFixture} document={resultWithCsvFixture.documents[0]} fetchCsv={fetchCsv} downloadUrl="/csv" onSelectFinding={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText("Money in")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry CSV connection" }));
    await screen.findByRole("img");
    expect(fetchCsv).toHaveBeenCalledTimes(2);
  });

  it("rejects an incompatible CSV locally and never fills it with JSON result data", async () => {
    panel(resultWithCsvFixture, "not,a,transaction,csv\r\n");
    expect(await screen.findByRole("alert")).toHaveTextContent("missing or duplicate schema columns");
    expect(screen.queryByText("Money in")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download transaction CSV" })).toBeInTheDocument();
  });

  it("shows missing values as missing, not zero, with explicit coverage disclosure", async () => {
    panel(resultWithCsvFixture, transactionCsvFixture(resultWithCsvFixture, {
      "row-newer": { credit: "", signed_movement: "", balance: "", value_date_iso: "" },
      "row-older": { balance: "", value_date_iso: "" },
    }));
    await screen.findByRole("img");
    expect(kpi("Money in")).toHaveTextContent("Not available");
    expect(kpi("Net movement")).toHaveTextContent("Not available");
    expect(screen.getByText(/Data coverage: 2 missing movements, 2 missing balances, 2 undated rows/)).toBeInTheDocument();
    expect(screen.getByText("No recorded balances available")).toBeInTheDocument();
    expect(document.querySelector(".balance-path")).toHaveAttribute("d", " ");
  });

  it("visibly discloses account/currency exclusions and keeps those rows out of totals", async () => {
    const original = resultWithCsvFixture.documents[0];
    const result: JobResult = { ...resultWithCsvFixture, documents: [{
      ...original, rows: original.rows.map((row, index) => index === 1 ? { ...row, currency: "USD", credit: "999.00" } : row),
    }] };
    panel(result);
    await screen.findByRole("img");
    expect(kpi("Net movement")).toHaveTextContent("125.00 GBP");
    expect(screen.getByText(/1 account\/currency exclusions/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByText(/Data coverage:/));
    expect(screen.getByText(/Different account or currency: source rows 2/)).toBeVisible();
  });

  it("does not fetch again when selecting a document or updating human review status", async () => {
    const { rerender, props, fetchCsv } = panel();
    await screen.findByRole("img");
    const changed = { ...props.result, findings: props.result.findings.map((finding) => ({ ...finding, review_status: "REVIEWED" as const })) };
    rerender(<FinancialMovementChart {...props} result={changed} document={{ ...props.document, source_id: "unselected-source" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("No exported transaction rows match this document's account and currency");
    rerender(<FinancialMovementChart {...props} result={changed} />);
    await screen.findByRole("img");
    expect(fetchCsv).toHaveBeenCalledTimes(1);
  });

  it("cancels the pending request when leaving results", () => {
    const fetchCsv = vi.fn(() => new Promise<string>(() => {}));
    const view = render(<FinancialMovementChart result={resultWithCsvFixture} document={resultWithCsvFixture.documents[0]} fetchCsv={fetchCsv} downloadUrl="/csv" onSelectFinding={vi.fn()} />);
    const signal = (fetchCsv.mock.calls[0] as unknown as [string, string, AbortSignal])[2];
    view.unmount();
    expect(signal.aborted).toBe(true);
  });

  it("bounds SVG detail and paginates exact values without dropping rows from totals", async () => {
    const user = userEvent.setup();
    const original = resultWithCsvFixture.documents[0];
    const result: JobResult = { ...resultWithCsvFixture,
      exports: { transactions_csv: { ...resultWithCsvFixture.exports!.transactions_csv!, row_count: 201 } },
      documents: [{ ...original, transaction_links: [], statement: { ...original.statement!, row_count: 201 }, rows: Array.from({ length: 201 }, (_, index) => ({
        ...original.rows[0], row_id: `row-${index}`, index, credit: "1.00", balance: String(201 - index),
      })) }],
    };
    panel(result);
    await screen.findByRole("img");
    expect(kpi("Net movement")).toHaveTextContent("201.00 GBP");
    expect(document.querySelectorAll(".movement-bar-in").length).toBeLessThanOrEqual(180);
    expect(screen.getByText(/Display groups up to 2 matching source rows/)).toBeInTheDocument();
    await user.click(screen.getByText(/View exact transaction values/));
    expect(screen.getByText("Rows 1–50 of 201")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next rows" }));
    await waitFor(() => expect(screen.getByText("Rows 51–100 of 201")).toBeInTheDocument());
  });
});
