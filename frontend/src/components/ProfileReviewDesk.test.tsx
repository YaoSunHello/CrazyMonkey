import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ProfileReviewDesk } from "./ProfileReviewDesk";
import {
  bootstrapFixture,
  capabilitiesFixture,
  resultFixture,
} from "../test/workspaceFixtures";

describe("ProfileReviewDesk", () => {
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
    const table = screen.getByRole("table", { name: "" });
    expect(within(table).getByText("OP-01 · link link-1")).toBeInTheDocument();
    expect(within(table).queryByText("OP-01 · date_sequence")).not.toBeInTheDocument();
    const evidence = screen.getByRole("heading", { name: "Running-balance link" }).closest("aside")!;
    expect(within(evidence).getByText("FAIL", { selector: "dd" })).toBeInTheDocument();
    expect(within(evidence).getByText("UNREVIEWED")).toBeInTheDocument();
  });
});
