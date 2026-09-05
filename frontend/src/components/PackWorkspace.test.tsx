import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PackWorkspace } from "./PackWorkspace";

const baseUrl = "http://pack.test";
const configured = { configured: true, provider: "gemini", model: "test-model", present: { LLM_API_KEY: true } };
const complete = {
  run_id: "saved-run", status: "COMPLETE", mode: "LIVE_MODEL", file_count: 1,
  processed_files: 1, model_call_count: 1, elapsed_seconds: 3.5,
  output_directory: "/local/pack/results",
  files: [{ relative_path: "dataset/report.xlsx", status: "COMPLETE", row_count: 1000,
    cell_count: 5000, page_count: 0, summary: "The workbook review is complete.", findings: [],
    limitations: ["The model reviewed a bounded selection of rows."] }],
};

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }
function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const mocked = vi.fn((url: RequestInfo | URL, init?: RequestInit) => handler(String(url), init));
  vi.stubGlobal("fetch", mocked);
  return mocked;
}
function folderFile(name: string, relativePath: string) {
  const file = new File(["sample"], name);
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("PackWorkspace", () => {
  it("restores the most recent saved run without requiring model configuration", async () => {
    const fetch = mockFetch(url => {
      if (url.endsWith("/config")) return response({ configured: false, provider: null, model: null });
      if (url.endsWith("/runs")) return response({ runs: [complete] });
      return response(complete);
    });
    render(<PackWorkspace baseUrl={baseUrl} />);
    expect(await screen.findByText("The workbook review is complete.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import and analyse" })).toBeDisabled();
    expect(screen.getByText("Full files imported. Model review uses bounded excerpts.")).toBeInTheDocument();
    expect(screen.getByText(/does not establish that every row, cell or page was checked/)).toBeInTheDocument();
    expect(screen.getByText(/1,000 rows · 5,000 cells/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`${baseUrl}/api/pack/runs/saved-run`, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
  });

  it("sends all supported nested files with matching relative paths and skips hidden files", async () => {
    let upload: FormData | undefined;
    const fetch = mockFetch((url, init) => {
      if (url.endsWith("/config")) return response(configured);
      if (init?.method === "POST") { upload = init.body as FormData; return response({ run_id: "new-run" }); }
      if (url.endsWith("/runs")) return response({ runs: [] });
      return response({ ...complete, run_id: "new-run" });
    });
    render(<PackWorkspace baseUrl={`${baseUrl}/`} />);
    await screen.findByText("Model configured on backend");
    const folder = screen.getByLabelText("Select dataset folder");
    expect(folder).toHaveAttribute("webkitdirectory");
    fireEvent.change(folder, { target: { files: [
      folderFile("report.xlsx", "Dataset/Workbooks/report.xlsx"),
      folderFile("README.md", "Dataset/Notes/README.md"),
      folderFile(".DS_Store", "Dataset/.DS_Store"),
      folderFile("note.txt", "Dataset/.hidden/note.txt"),
      folderFile("photo.png", "Dataset/photo.png"),
    ] } });
    expect(screen.getByText("3 hidden or unsupported files were skipped.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Files selected for import" })).getAllByRole("listitem")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Review instruction"), { target: { value: "Check these source documents." } });
    fireEvent.click(screen.getByRole("button", { name: "Import and analyse 2 files" }));
    await screen.findByText("The workbook review is complete.");
    expect(upload?.getAll("relative_paths")).toEqual(["Dataset/Workbooks/report.xlsx", "Dataset/Notes/README.md"]);
    expect(upload?.getAll("files").map(item => (item as File).name)).toEqual(["report.xlsx", "README.md"]);
    expect(upload?.get("instruction")).toBe("Check these source documents.");
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.headers).toBeUndefined();
  });

  it("adds individual files, deduplicates repeated paths and permits removing selected files", async () => {
    mockFetch(url => url.endsWith("/config") ? response(configured) : response({ runs: [] }));
    render(<PackWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Model configured on backend");
    const file = new File(["text"], "README.txt");
    const input = screen.getByLabelText("Select dataset files");
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.change(input, { target: { files: [file] } });
    expect(within(screen.getByRole("list", { name: "Files selected for import" })).getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove README.txt" }));
    expect(screen.queryByRole("list", { name: "Files selected for import" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import and analyse" })).toBeDisabled();
  });

  it("polls active runs and displays terminal partial failures without hiding completed files", async () => {
    let polls = 0;
    mockFetch(url => {
      if (url.endsWith("/config")) return response(configured);
      if (url.endsWith("/runs")) return response({ runs: [{ ...complete, status: "ANALYSING" }] });
      polls += 1;
      if (polls === 1) return response({ ...complete, status: "ANALYSING", processed_files: 0, files: [{ ...complete.files[0], status: "ANALYSING", summary: "" }] });
      return response({ ...complete, status: "COMPLETE_WITH_ERRORS", file_count: 2, processed_files: 2,
        files: [complete.files[0], { relative_path: "dataset/scanned.pdf", status: "FAILED", page_count: 3,
          summary: "", error: "No usable text was extracted.", limitations: ["An image-only document needs OCR."], findings: [] }] });
    });
    render(<PackWorkspace baseUrl={baseUrl} />);
    await screen.findByRole("progressbar", { name: "Files processed" });
    expect(await screen.findByText("No usable text was extracted.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("The workbook review is complete.")).toBeInTheDocument();
    expect(screen.getByText("An image-only document needs OCR.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(polls).toBe(2);
  });

  it("keeps selected files after an upload failure and never displays the raw error payload", async () => {
    mockFetch((url, init) => {
      if (url.endsWith("/config")) return response(configured);
      if (init?.method === "POST") return response({ detail: "RAW_SERVER_DETAILS_MUST_NOT_RENDER" }, 500);
      return response({ runs: [] });
    });
    render(<PackWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Model configured on backend");
    fireEvent.change(screen.getByLabelText("Select dataset files"), { target: { files: [new File(["pdf"], "report.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Import and analyse 1 file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 500");
    expect(screen.getByRole("button", { name: "Import and analyse 1 file" })).toBeEnabled();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("RAW_SERVER_DETAILS_MUST_NOT_RENDER");
  });

  it("renders findings, paths and summaries as plain text", async () => {
    const hostile = '<img src="x" onerror="alert(1)">';
    const run = { ...complete, files: [{ ...complete.files[0], summary: hostile, role: "WORKFLOW_CONTEXT",
      suggested_actions: ["Compare the referenced worksheet with the source contract."],
      findings: [{ title: "Check this difference", status: "REVIEW_REQUIRED", severity: "HIGH",
        explanation: "A source comparison is needed.", evidence_ids: ["ev-source-1"] }] }] };
    mockFetch(url => url.endsWith("/config") ? response(configured) : url.endsWith("/runs") ? response({ runs: [run] }) : response(run));
    render(<PackWorkspace baseUrl={baseUrl} />);
    expect(await screen.findByText(hostile)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Findings and review limits (1 finding)"));
    expect(screen.getByText("A source comparison is needed.")).toBeVisible();
    expect(screen.getByText("ev-source-1")).toBeVisible();
    expect(screen.getByText("Workflow context")).toBeVisible();
    expect(screen.getByText("Compare the referenced worksheet with the source contract.")).toBeVisible();
    const evidenceLink = screen.getByRole("link", { name: "ev-source-1" });
    expect(evidenceLink).toHaveAttribute("href", `${baseUrl}/api/pack/runs/saved-run/evidence/ev-source-1`);
    expect(evidenceLink).toHaveAttribute("target", "_blank");
    expect(evidenceLink).toHaveAttribute("rel", "noreferrer");
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });

  it("shows suggested actions without findings and encodes source evidence paths", async () => {
    const run = { ...complete, run_id: "run with spaces", files: [
      { ...complete.files[0], relative_path: "notes.txt", findings: [], limitations: [], role: "REFERENCE", suggested_actions: ["Locate the signed agreement."] },
      { ...complete.files[0], findings: [{ title: "Document comparison", severity: "INFO", explanation: "Check the original page.", evidence_ids: ["ev/source?1"] }] },
    ] };
    mockFetch(url => url.endsWith("/config") ? response(configured) : url.endsWith("/runs") ? response({ runs: [run] }) : response(run));
    render(<PackWorkspace baseUrl={baseUrl} />);
    await screen.findByText("notes.txt");
    fireEvent.click(screen.getByText("Findings and review limits (0 findings)"));
    expect(screen.getByText("Reference")).toBeVisible();
    expect(screen.getByText("Locate the signed agreement.")).toBeVisible();
    fireEvent.click(screen.getByText("Findings and review limits (1 finding)"));
    expect(screen.getByRole("link", { name: "ev/source?1" })).toHaveAttribute("href", `${baseUrl}/api/pack/runs/run%20with%20spaces/evidence/ev%2Fsource%3F1`);
    expect(screen.getByText("INFO")).toBeVisible();
    expect(screen.queryByText("INFO ·")).not.toBeInTheDocument();
  });

  it("loads saved results independently when the config endpoint fails", async () => {
    mockFetch(url => url.endsWith("/config") ? response({}, 503) : url.endsWith("/runs") ? response({ runs: [complete] }) : response(complete));
    render(<PackWorkspace baseUrl={baseUrl} />);
    await screen.findByText("The workbook review is complete.");
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot connect to the model configuration service");
    expect(screen.getByRole("button", { name: "Import and analyse" })).toBeDisabled();
  });

  it("does not show a stale response after switching saved runs", async () => {
    let releaseOld: ((response: Response) => void) | undefined;
    mockFetch(url => {
      if (url.endsWith("/config")) return response(configured);
      if (url.endsWith("/runs")) return response({ runs: [{ ...complete, run_id: "old-run" }, complete] });
      if (url.endsWith("/old-run")) return new Promise<Response>(resolve => { releaseOld = resolve; });
      return response(complete);
    });
    render(<PackWorkspace baseUrl={baseUrl} />);
    await waitFor(() => expect(releaseOld).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /saved-run/ }));
    await screen.findByText("The workbook review is complete.");
    releaseOld?.(response({ ...complete, run_id: "old-run", files: [{ ...complete.files[0], summary: "Stale old result" }] }));
    await waitFor(() => expect(screen.queryByText("Stale old result")).not.toBeInTheDocument());
  });
});
