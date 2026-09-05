import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatementWorkspace } from "./StatementWorkspace";

const baseUrl = "http://statement.test";

const validationWorkflow = {
  id: "statement-validation",
  label: "Bank statement validation",
  description: "Check statement arithmetic without a model.",
  requiresWorkbook: false,
  requiresModel: false,
};

const journalWorkflow = {
  id: "journal-entries",
  label: "Bank statements to journal entries",
  description: "Resolve statement rows and produce journal entries.",
  requiresWorkbook: true,
  requiresModel: true,
};

function configuration(overrides: Record<string, unknown> = {}) {
  return {
    backendReachable: true,
    llmConfigured: true,
    daytonaConfigured: true,
    model: { configured: true, provider: "test", model: "test-model" },
    workflows: [validationWorkflow, journalWorkflow],
    ...overrides,
  };
}

function completedJob(overrides: Record<string, unknown> = {}) {
  return {
    jobId: "statement-00000000000000000000000000000001",
    state: "COMPLETED",
    workflowId: "statement-validation",
    fileCount: 0,
    processedFiles: 0,
    modelCallAttempted: false,
    modelCallSucceeded: null,
    files: [],
    artifacts: [],
    ...overrides,
  };
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installBackend(options: {
  config?: ReturnType<typeof configuration>;
  onPost?: (form: FormData) => Response | Promise<Response>;
  onGetJob?: () => Response | Promise<Response>;
} = {}) {
  const mocked = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === `${baseUrl}/api/v1/statement-jobs/config`) {
      return json(options.config ?? configuration());
    }
    if (url === `${baseUrl}/api/profiles`) return json([]);
    if (url === `${baseUrl}/api/v1/statement-jobs` && init?.method === "POST") {
      return options.onPost?.(init.body as FormData) ?? json(completedJob());
    }
    if (url.startsWith(`${baseUrl}/api/v1/statement-jobs/`) && !init?.method) {
      return options.onGetJob?.() ?? json(completedJob());
    }
    throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
  });
  vi.stubGlobal("fetch", mocked);
  return mocked;
}

function sourceFile(contents: string, name: string) {
  return new File([contents], name, {
    type: name.endsWith(".pdf")
      ? "application/pdf"
      : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function folderFile(contents: string, name: string, relativePath: string) {
  const file = sourceFile(contents, name);
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("StatementWorkspace", () => {
  it("treats one or two PDFs as bank statements and enables validation without NAV or LPA inputs", async () => {
    installBackend();
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    const input = screen.getByLabelText("Select bank statement files");
    fireEvent.change(input, {
      target: { files: [sourceFile("first", "20260331_NI_ABF_I_SCSP_CALDER_EUR_0894.pdf")] },
    });

    let selection = screen.getByRole("list", { name: "Original files selected for processing" });
    expect(within(selection).getAllByText(/Bank statement/)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Start processing 1 statement" })).toBeEnabled();
    expect(selection).not.toHaveTextContent(/NAV workbook|Investor register|LPA/i);

    fireEvent.change(input, {
      target: { files: [sourceFile("second", "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf")] },
    });

    selection = screen.getByRole("list", { name: "Original files selected for processing" });
    expect(within(selection).getAllByText(/Bank statement/)).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Start processing 2 statements" })).toBeEnabled();
    expect(screen.queryByText(/Still required: LPA/i)).not.toBeInTheDocument();
  });

  it("preserves reversed upload order while binding every file to its own client identifier", async () => {
    let upload: FormData | undefined;
    installBackend({
      onPost: form => {
        upload = form;
        return json(completedJob({ fileCount: 2, processedFiles: 2 }));
      },
    });
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    const second = sourceFile("second-file-bytes", "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf");
    const first = sourceFile("first-file-bytes", "20260331_NI_ABF_I_SCSP_CALDER_EUR_0894.pdf");
    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [second, first] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start processing 2 statements" }));

    await screen.findByText(/Job ID:/);
    const files = upload?.getAll("files") as File[];
    const fileIds = upload?.getAll("fileIds").map(String) ?? [];
    const manifest = JSON.parse(String(upload?.get("manifest"))) as Array<{
      clientFileId: string;
      filename: string;
      relativePath: string;
      role: string;
    }>;
    expect(files.map(file => file.name)).toEqual([second.name, first.name]);
    expect(fileIds).toHaveLength(2);
    expect(new Set(fileIds).size).toBe(2);
    expect(manifest).toEqual([
      { clientFileId: fileIds[0], filename: second.name, relativePath: second.name, role: "BANK_STATEMENT" },
      { clientFileId: fileIds[1], filename: first.name, relativePath: first.name, role: "BANK_STATEMENT" },
    ]);
  });

  it("requires exactly one reference XLSX for the journal workflow, then enables Start", async () => {
    installBackend();
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    fireEvent.change(screen.getByLabelText("Processing workflow"), { target: { value: "journal-entries" } });
    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [sourceFile("pdf", "Calder_EUR_0894.pdf")] },
    });
    expect(screen.getByText(/needs the supplied reference workbook/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start processing 1 statement" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [sourceFile("xlsx", "Calder_reference_tables.xlsx")] },
    });
    expect(screen.getByText(/Reference workbook/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start processing 1 statement" })).toBeEnabled();
  });

  it("sends exact files, manifest, workflow and idempotency key, and double-clicking starts only one job", async () => {
    let upload: FormData | undefined;
    const fetch = installBackend({
      onPost: form => {
        upload = form;
        return json(completedJob({ fileCount: 2, processedFiles: 2 }));
      },
    });
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    const one = sourceFile("one-original", "one.pdf");
    const two = sourceFile("two-original", "two.pdf");
    fireEvent.change(screen.getByLabelText("Select bank statement files"), { target: { files: [one, two] } });
    const start = screen.getByRole("button", { name: "Start processing 2 statements" });
    fireEvent.click(start);
    fireEvent.click(start);

    await screen.findByText(/Job ID:/);
    const posts = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(upload?.get("workflowId")).toBe("statement-validation");
    expect(String(upload?.get("clientRequestId"))).toMatch(/^[A-Za-z0-9][A-Za-z0-9.\-_:]+$/);
    expect(upload?.getAll("files").map(item => (item as File).name)).toEqual(["one.pdf", "two.pdf"]);
    expect(await (upload?.getAll("files")[0] as File).text()).toBe("one-original");
    expect(await (upload?.getAll("files")[1] as File).text()).toBe("two-original");
    const manifest = JSON.parse(String(upload?.get("manifest")));
    expect(manifest).toEqual([
      expect.objectContaining({ filename: "one.pdf", relativePath: "one.pdf", role: "BANK_STATEMENT" }),
      expect.objectContaining({ filename: "two.pdf", relativePath: "two.pdf", role: "BANK_STATEMENT" }),
    ]);
  });

  it("shows backend unavailable and never offers fixture data", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    render(<StatementWorkspace baseUrl={baseUrl} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
    expect(screen.getByRole("button", { name: "Start processing" })).toBeDisabled();
    expect(screen.queryByText(/synthetic demo|fixture result|LP03/i)).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("filters README, hidden, cache and unsupported folder entries while retaining same-name files in distinct paths", async () => {
    installBackend();
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    fireEvent.change(screen.getByLabelText("Select bank statement folder"), {
      target: { files: [
        folderFile("same-size", "statement.pdf", "Dataset/A/statement.pdf"),
        folderFile("same-size", "statement.pdf", "Dataset/B/statement.pdf"),
        folderFile("readme", "README.md", "Dataset/README.md"),
        folderFile("secret", "secret.pdf", "Dataset/.hidden/secret.pdf"),
        folderFile("cached", "cached.pdf", "Dataset/cache/cached.pdf"),
        folderFile("image", "photo.png", "Dataset/photo.png"),
      ] },
    });

    const selection = screen.getByRole("list", { name: "Original files selected for processing" });
    expect(within(selection).getAllByRole("listitem")).toHaveLength(2);
    expect(selection).toHaveTextContent("Dataset/A/statement.pdf");
    expect(selection).toHaveTextContent("Dataset/B/statement.pdf");
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("4 files were skipped");
    expect(notice).toHaveTextContent("README is not source evidence");
    expect(notice).toHaveTextContent("hidden/cache folder");
    expect(notice).toHaveTextContent("unsupported type");
  });

  it("renders a failed equation, evidence, source link and the backend-provided artifact", async () => {
    const jobId = "statement-00000000000000000000000000000002";
    const fileId = "file-source-0894";
    installBackend({
      onPost: () => json(completedJob({
        jobId,
        fileCount: 1,
        processedFiles: 1,
        files: [{
          fileId,
          relativePath: "Calder_EUR_0894.pdf",
          role: "BANK_STATEMENT",
          status: "COMPLETED_WITH_ISSUES",
          sourceSha256: "a".repeat(64),
          account: "EUR_0894",
          currency: "EUR",
          rowCount: 2,
          closingBalance: "70.00",
          checks: [{
            name: "balance_chain",
            status: "FAIL",
            message: "The next balance does not foot.",
            evidence: {
              equation: "100.00 - 20.00 = 80.00",
              expected: "80.00",
              actual: "70.00",
              delta: "-10.00",
              citation: "p1 @ (35,348)-(725,355)",
            },
          }],
          rows: [],
        }],
        artifacts: [{
          id: "result-json",
          filename: "result.json",
          downloadUrl: `/api/v1/statement-jobs/${jobId}/artifacts/result-json`,
        }],
      })),
    });
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");
    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [sourceFile("pdf", "Calder_EUR_0894.pdf")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start processing 1 statement" }));

    expect(await screen.findByText("Balance chain")).toBeInTheDocument();
    const checks = screen.getByRole("region", { name: "Verification checks for Calder_EUR_0894.pdf" });
    expect(checks).toHaveTextContent("FAIL");
    expect(checks).toHaveTextContent("100.00 - 20.00 = 80.00");
    expect(checks).toHaveTextContent("expected: 80.00");
    expect(checks).toHaveTextContent("actual: 70.00");
    expect(checks).toHaveTextContent("delta: -10.00");
    expect(checks).toHaveTextContent("p1 @ (35,348)-(725,355)");
    expect(screen.getByRole("link", { name: /Open source/ })).toHaveAttribute(
      "href",
      `${baseUrl}/api/v1/statement-jobs/${jobId}/sources/${fileId}`,
    );
    expect(screen.getByRole("link", { name: /Download JSON/ })).toHaveAttribute(
      "href",
      `${baseUrl}/api/v1/statement-jobs/${jobId}/artifacts/result-json`,
    );
  });

  it("blocks model-backed processing when backend model configuration is missing", async () => {
    installBackend({ config: configuration({ llmConfigured: false }) });
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");
    fireEvent.change(screen.getByLabelText("Processing workflow"), { target: { value: "journal-entries" } });
    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [sourceFile("pdf", "Calder_EUR_0894.pdf"), sourceFile("xlsx", "references.xlsx")] },
    });

    expect(screen.getByText(/backend model is not configured/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start processing 1 statement" })).toBeDisabled();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
  });

  it("restores the sessionStorage-saved job from the backend after remounting", async () => {
    const jobId = "statement-00000000000000000000000000000003";
    window.sessionStorage.setItem("crazymonkey.statement-job-id", jobId);
    const fetch = installBackend({
      onGetJob: () => json(completedJob({
        jobId,
        workflowId: "journal-entries",
        modelRequested: true,
        modelCallAttempted: true,
        modelCallSucceeded: true,
      })),
    });

    const { unmount } = render(<StatementWorkspace baseUrl={baseUrl} />);

    expect(await screen.findByText(new RegExp(jobId))).toBeInTheDocument();
    expect(screen.getByLabelText("Processing workflow")).toHaveValue("journal-entries");
    expect(fetch).toHaveBeenCalledWith(
      `${baseUrl}/api/v1/statement-jobs/${jobId}`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    unmount();
    render(<StatementWorkspace baseUrl={baseUrl} />);
    expect(await screen.findByText(new RegExp(jobId))).toBeInTheDocument();
  });

  it("locks both upload inputs and the workflow selector while a queued job owns polling", async () => {
    installBackend({
      onPost: () => json(completedJob({
        state: "QUEUED",
        fileCount: 1,
        processedFiles: 0,
        timeline: [{ state: "QUEUED", at: "2026-09-05T20:00:00Z" }],
      }), 202),
      onGetJob: () => json(completedJob({
        state: "QUEUED",
        fileCount: 1,
        processedFiles: 0,
        timeline: [{ state: "QUEUED", at: "2026-09-05T20:00:00Z" }],
      })),
    });
    render(<StatementWorkspace baseUrl={baseUrl} />);
    await screen.findByText("Backend connected");

    fireEvent.change(screen.getByLabelText("Select bank statement files"), {
      target: { files: [sourceFile("pdf", "Calder_EUR_0894.pdf")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start processing 1 statement" }));
    await screen.findByText(/Job ID:/);

    expect(screen.getByLabelText("Select bank statement files")).toBeDisabled();
    expect(screen.getByLabelText("Select bank statement folder")).toBeDisabled();
    expect(screen.getByLabelText("Processing workflow")).toBeDisabled();
  });

  it("renders lifecycle labels from the timeline returned by the backend", async () => {
    const jobId = "statement-00000000000000000000000000000004";
    window.sessionStorage.setItem("crazymonkey.statement-job-id", jobId);
    installBackend({
      onGetJob: () => json(completedJob({
        jobId,
        state: "COMPLETED_WITH_ISSUES",
        timeline: [
          { state: "QUEUED", at: "2026-09-05T20:00:00Z" },
          { state: "PROCESSING", at: "2026-09-05T20:00:01Z" },
          { state: "COMPLETED_WITH_ISSUES", at: "2026-09-05T20:00:02Z" },
        ],
      })),
    });
    render(<StatementWorkspace baseUrl={baseUrl} />);

    const timeline = await screen.findByRole("list", { name: "Actual job lifecycle" });
    expect(within(timeline).getByText("Queued")).toBeInTheDocument();
    expect(within(timeline).getByText("Processing original files")).toBeInTheDocument();
    expect(within(timeline).getByText("Completed — review issues found")).toBeInTheDocument();
  });
});
