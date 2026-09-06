import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ProfileReviewDesk } from "./ProfileReviewDesk";
import { resultWithCsvFixture, transactionCsvFixture } from "../test/transactionCsvFixtures";
import {
  bootstrapFixture,
  capabilitiesFixture,
  resultFixture,
} from "../test/workspaceFixtures";

describe("ProfileReviewDesk", () => {
  it("keeps evidence available after CSV failure and connects chart findings back to the existing desk", async () => {
    const user = userEvent.setup();
    const fetchCsv = vi.fn().mockRejectedValueOnce(new Error("CSV connection interrupted")).mockResolvedValue(transactionCsvFixture());
    render(<ProfileReviewDesk result={resultWithCsvFixture} profileLabel="Bank statement validation"
      connection={bootstrapFixture.connection} onReview={vi.fn()} onBack={vi.fn()}
      sourceUrl={(id) => `/sources/${id}`} artifactUrl={(id) => `/artifacts/${id}`}
      fetchTransactionCsv={fetchCsv} transactionCsvUrl="/api/ui/v1/jobs/job-123/transactions.csv" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("CSV connection interrupted");
    expect(screen.getByRole("link", { name: "Open original PDF" })).toHaveAttribute("href", "/sources/source-1");
    expect(screen.getByRole("heading", { name: "Backend-supplied calculation" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry CSV connection" }));
    await screen.findByRole("img", { name: /Recorded balance and signed movements/ });
    await user.type(screen.getByRole("searchbox", { name: "Search transactions and checks" }), "no matching finding");
    expect(screen.getByText("No checks match this view.")).toBeInTheDocument();
    await user.click(screen.getByText(/View exact transaction values/));
    await user.click(screen.getByRole("button", { name: "Inspect FAIL · row 1" }));
    expect(screen.getByRole("searchbox", { name: "Search transactions and checks" })).toHaveValue("");
    expect(screen.queryByText("No checks match this view.")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Backend-supplied calculation" })).toBeInTheDocument();
    expect(fetchCsv).toHaveBeenCalledTimes(2);
  });

  it("keeps the original PDF and statement metadata available for an unresolved check without a page citation", () => {
    const sha256 = "1234567890abcdef".repeat(4);
    const atlasId = "atlas-document-1234567890abcdef";
    const document = {
      ...resultFixture.documents[0],
      sha256,
      atlas: { document_id: atlasId },
      transaction_links: [],
      checks: [{
        finding_id: "printed-opening",
        name: "printed_openings",
        scope: "statement",
        status: "UNRESOLVED" as const,
        detail: "No Balance brought forward marker is printed.",
        evidence: "No marker was found in the source PDF.",
        review_status: "UNREVIEWED" as const,
      }],
      statement: { ...resultFixture.documents[0].statement!, row_count: 16, closing_balance: "20088.32" },
    };
    render(<ProfileReviewDesk
      result={{ ...resultFixture, documents: [document] }}
      profileLabel="Bank statement validation"
      connection={bootstrapFixture.connection}
      onReview={vi.fn()}
      onBack={vi.fn()}
      sourceUrl={(sourceId) => `/api/ui/v1/jobs/job-123/sources/${sourceId}`}
      artifactUrl={(artifactId) => `/api/ui/v1/jobs/job-123/artifacts/${artifactId}`}
    />);

    expect(screen.getByRole("heading", { name: "printed openings" })).toBeInTheDocument();
    expect(screen.getByText("No structured page citation was supplied for this check.")).toBeInTheDocument();
    const original = screen.getByRole("region", { name: "Original document" });
    expect(within(original).getByRole("link", { name: "Open original PDF" })).toHaveAttribute("href", "/api/ui/v1/jobs/job-123/sources/source-1");
    expect(within(original).getByText("00001234")).toBeInTheDocument();
    expect(within(original).getByText("GBP")).toBeInTheDocument();
    expect(within(original).getByText("16")).toBeInTheDocument();
    expect(within(original).getByText("20,088.32")).toBeInTheDocument();
    expect(within(original).getByTitle(sha256)).toHaveTextContent("1234567890abcdef…90abcdef");
    expect(within(original).getByTitle(atlasId)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download JSON result" })).toHaveAttribute("href", "/api/ui/v1/jobs/job-123/artifacts/result-json");
  });

  it("shows cannot-verify as an unresolved item requiring human review", () => {
    const original = resultFixture.documents[0];
    const document = {
      ...original,
      computational_outcome: "CANNOT_VERIFY" as const,
      transaction_links: [],
      checks: [{
        finding_id: "missing-opening",
        name: "printed_openings",
        scope: "statement",
        status: "CANNOT_VERIFY" as const,
        detail: "The statement does not print an opening marker.",
        evidence: "",
        review_status: "UNREVIEWED" as const,
      }],
    };
    render(<ProfileReviewDesk result={{ ...resultFixture, documents: [document] }}
      profileLabel="Bank statement validation" connection={bootstrapFixture.connection}
      onReview={vi.fn()} onBack={vi.fn()} sourceUrl={() => "/source"} artifactUrl={() => "/artifact"} />);
    expect(screen.getByText("Unresolved / cannot verify").nextElementSibling).toHaveTextContent("1");
    expect(screen.getAllByText("CANNOT VERIFY").length).toBeGreaterThan(0);
    expect(screen.getByText("Needs review").nextElementSibling).toHaveTextContent("1");
  });

  it("renders exact backend-supplied decimal operands and opens the cited source page without inventing a highlight", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(
      <ProfileReviewDesk
        result={resultFixture}
        profileLabel="Journal entry validation"
        connection={bootstrapFixture.connection}
        capabilities={capabilitiesFixture}
        onReview={vi.fn()}
        onBack={vi.fn()}
        sourceUrl={(sourceId) => `/api/ui/v1/jobs/job-123/sources/${sourceId}`}
        artifactUrl={(artifactId) => `/api/ui/v1/jobs/job-123/artifacts/${artifactId}`}
      />,
    );

    const calculation = screen.getByRole("heading", { name: "Backend-supplied calculation" }).closest("section")!;
    expect(within(calculation).getByText("1,000.00 GBP")).toBeInTheDocument();
    expect(within(calculation).getByText("125.00 GBP")).toBeInTheDocument();
    expect(within(calculation).getByText("875.00 GBP")).toBeInTheDocument();
    expect(within(calculation).getByText("860.00 GBP")).toBeInTheDocument();
    expect(within(calculation).getByText("15.00 GBP")).toBeInTheDocument();
    expect(within(calculation).getByText(/exact decimal strings returned by the verifier/)).toBeInTheDocument();

    const source = screen.getByRole("heading", { name: "Source evidence" }).closest("section")!;
    expect(within(source).getByText("Page 3 · bounding box (42, 100)–(516, 119)")).toBeInTheDocument();
    expect(within(source).getByText("Page 3 · bounding box (42, 120)–(516, 139)")).toBeInTheDocument();
    expect(within(source).getByText(/No highlight is drawn unless the viewer can honour the real coordinates/)).toBeInTheDocument();
    await user.click(within(source).getByRole("button", { name: "Open balance row source page" }));
    expect(open).toHaveBeenCalledWith(
      "/api/ui/v1/jobs/job-123/sources/source-1#page=3",
      "_blank",
      "noopener,noreferrer",
    );
    await user.click(within(source).getByRole("button", { name: "Open comparison row source page" }));
    expect(open).toHaveBeenCalledTimes(2);
  });

  it("only enables the generated JSON artifact and explains why report/workbook actions are gated", () => {
    render(
      <ProfileReviewDesk
        result={resultFixture}
        profileLabel="Journal entry validation"
        connection={bootstrapFixture.connection}
        capabilities={capabilitiesFixture}
        onReview={vi.fn()}
        onBack={vi.fn()}
        sourceUrl={() => "/source"}
        artifactUrl={(artifactId) => `/api/ui/v1/jobs/job-123/artifacts/${artifactId}`}
      />,
    );

    const json = screen.getByRole("link", { name: "Download JSON result" });
    expect(json).toHaveAttribute("href", "/api/ui/v1/jobs/job-123/artifacts/result-json");
    expect(json).toHaveAttribute("download", "job-123-result.json");
    expect(screen.getByRole("button", { name: "Download review workbook" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Download report" })).toBeDisabled();
    expect(screen.getByText("The backend does not generate a workbook.")).toBeInTheDocument();
    expect(screen.getByText("The backend does not generate a report.")).toBeInTheDocument();
  });

  it("shows a fatal terminal error without claiming verification completed", () => {
    render(
      <ProfileReviewDesk
        result={{
          ...resultFixture,
          processing_state: "FAILED",
          error: "RuntimeError: parser unavailable",
          documents: [],
          findings: [],
          artifacts: [],
        }}
        profileLabel="Journal entry validation"
        connection={bootstrapFixture.connection}
        capabilities={capabilitiesFixture}
        onReview={vi.fn()}
        onBack={vi.fn()}
        sourceUrl={() => "/source"}
        artifactUrl={() => "/artifact"}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Processing failed; no successful verification result is being claimed.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("RuntimeError: parser unavailable");
    expect(screen.queryByText("Deterministic verification complete.")).not.toBeInTheDocument();
  });

  it("filters to failed checks while retaining computational and human-review states separately", async () => {
    const user = userEvent.setup();
    render(
      <ProfileReviewDesk
        result={resultFixture}
        profileLabel="Journal entry validation"
        connection={bootstrapFixture.connection}
        capabilities={capabilitiesFixture}
        onReview={vi.fn()}
        onBack={vi.fn()}
        sourceUrl={() => "/source"}
        artifactUrl={() => "/artifact"}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Failed checks" }));
    expect(screen.getByRole("button", { name: "Failed checks" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
    const table = screen.getByRole("table", { name: "" });
    expect(within(table).getByText("OP-01 · link link-1")).toBeInTheDocument();
    expect(within(table).queryByText("OP-01 · date_sequence")).not.toBeInTheDocument();
    const evidence = screen.getByRole("heading", { name: "Running-balance link" }).closest("aside")!;
    expect(within(evidence).getByText("FAIL", { selector: "dd" })).toBeInTheDocument();
    expect(within(evidence).getByText("UNREVIEWED")).toBeInTheDocument();
  });

  it("keeps a failed document with no findings selected instead of showing evidence from another document", async () => {
    const user = userEvent.setup();
    const failedDocument = {
      ...resultFixture.documents[0],
      source_id: "source-broken",
      client_file_id: "client-broken",
      relative_path: "statements/broken.pdf",
      filename: "broken.pdf",
      processing_state: "FAILED" as const,
      computational_outcome: null,
      error: "PDFSyntaxError: cross-reference table could not be read",
      statement: undefined,
      rows: [],
      transaction_links: [],
      checks: [],
    };
    render(
      <ProfileReviewDesk
        result={{ ...resultFixture, processing_state: "PARTIAL", documents: [resultFixture.documents[0], failedDocument] }}
        profileLabel="Journal entry validation"
        connection={bootstrapFixture.connection}
        capabilities={capabilitiesFixture}
        onReview={vi.fn()}
        onBack={vi.fn()}
        sourceUrl={() => "/source"}
        artifactUrl={() => "/artifact"}
      />,
    );

    await user.click(screen.getByRole("button", { name: /broken\.pdf/ }));

    const evidence = screen.getByRole("heading", { name: "broken.pdf" }).closest("aside")!;
    expect(within(evidence).getByRole("heading", { name: "Document processing failed" })).toBeInTheDocument();
    expect(within(evidence).getByRole("alert")).toHaveTextContent("PDFSyntaxError: cross-reference table could not be read");
    expect(within(evidence).queryByRole("heading", { name: "Running-balance link" })).not.toBeInTheDocument();
    expect(within(evidence).getByRole("link", { name: "Open original PDF" })).toHaveAttribute("href", "/source");
  });
});
