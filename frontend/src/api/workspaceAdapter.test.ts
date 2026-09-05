import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpWorkspaceAdapter, isTerminalJob } from "./workspaceAdapter";
import {
  bootstrapFixture,
  capabilitiesFixture,
  completedJobFixture,
  replayFixture,
  resultFixture,
  startFixture,
} from "../test/workspaceFixtures";
import type { InventoryEntry } from "../workspaceTypes";

afterEach(() => {
  vi.unstubAllGlobals();
});

function profilesResponse() {
  return bootstrapFixture.profiles;
}

function replayListResponse() {
  return { replays: bootstrapFixture.replays, note: "Committed recorded results." };
}

function serveBootstrap(overrides: Partial<Record<string, Response | Error>> = {}) {
  const defaults: Record<string, Response | Error> = {
    "/health": Response.json({ status: "ok" }),
    "/api/profiles": Response.json(profilesResponse()),
    "/api/ui/v1/capabilities": Response.json(capabilitiesFixture),
    "/api/ui/v1/replays": Response.json(replayListResponse()),
  };
  const responses = { ...defaults, ...overrides };
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const path = new URL(String(input)).pathname;
    const configured = responses[path];
    if (!configured) throw new Error(`Unexpected request: ${path}`);
    if (configured instanceof Error) throw configured;
    return configured;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("HttpWorkspaceAdapter bootstrap", () => {
  it("only reports CONNECTED when health, profile discovery and bridge capabilities align", async () => {
    const fetchMock = serveBootstrap();
    const adapter = new HttpWorkspaceAdapter("https://review.test/");

    const boot = await adapter.bootstrap();

    expect(boot.connection).toMatchObject({ state: "CONNECTED", label: "Backend connected" });
    expect(boot.connection.detail).toContain("LOCAL_DETERMINISTIC · 0 model calls");
    expect(boot.profiles.map((profile) => profile.id)).toEqual(["journal-entries"]);
    expect(boot.capabilities?.api_version).toBe("ui.v1");
    expect(boot.replays).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual(expect.arrayContaining([
      "https://review.test/health",
      "https://review.test/api/profiles",
      "https://review.test/api/ui/v1/capabilities",
      "https://review.test/api/ui/v1/replays",
    ]));
  });

  it("uses GET /api/profiles labels while hiding profiles the deterministic bridge cannot start", async () => {
    serveBootstrap({
      "/api/profiles": Response.json([
        ...profilesResponse(),
        {
          ...profilesResponse()[0],
          id: "agent-only-screening",
          label: "Agent-only screening",
          documents: "None",
        },
      ]),
    });

    const boot = await new HttpWorkspaceAdapter("https://review.test").bootstrap();

    expect(boot.connection.state).toBe("CONNECTED");
    expect(boot.profiles.map((profile) => [profile.id, profile.label])).toEqual([
      ["journal-entries", "Journal entry validation"],
    ]);
  });

  it("reports HEALTH_ONLY rather than silently falling back when the bridge is missing", async () => {
    serveBootstrap({
      "/api/ui/v1/capabilities": Response.json({ detail: "Not found" }, { status: 404 }),
    });

    const boot = await new HttpWorkspaceAdapter("https://review.test").bootstrap();

    expect(boot.connection.state).toBe("HEALTH_ONLY");
    expect(boot.connection.detail).toContain("/health");
    expect(boot.issues).toContain("UI bridge unavailable: Not found");
    expect(boot.capabilities).toBeUndefined();
  });

  it("rejects a nominal bridge that advertises a workflow absent from GET /api/profiles", async () => {
    serveBootstrap({
      "/api/profiles": Response.json([{ ...profilesResponse()[0], id: "unknown-profile" }]),
    });

    const boot = await new HttpWorkspaceAdapter("https://review.test").bootstrap();

    expect(boot.connection.state).toBe("HEALTH_ONLY");
    expect(boot.issues).toContain("UI bridge capabilities advertise an unknown or duplicate workflow.");
  });

  it("reports UNAVAILABLE when the health check cannot be reached while preserving diagnostics", async () => {
    serveBootstrap({ "/health": new TypeError("network offline") });

    const boot = await new HttpWorkspaceAdapter("https://review.test").bootstrap();

    expect(boot.connection.state).toBe("UNAVAILABLE");
    expect(boot.issues[0]).toBe("Backend health check failed.");
  });
});

describe("HttpWorkspaceAdapter requests", () => {
  function sourceEntry(): InventoryEntry {
    const file = new File(["source bytes"], "statement.pdf", { type: "application/pdf" });
    return {
      clientFileId: "client-source",
      file,
      relativePath: "pack/statement.pdf",
      filename: file.name,
      sizeBytes: file.size,
      contentType: file.type,
      status: "SUPPORTED",
      reason: "Supported source document.",
      selected: true,
      purpose: "SOURCE",
    };
  }

  it("uploads selected bytes in manifest order with relative paths, purposes and an idempotency key", async () => {
    const source = new File(["source bytes"], "statement.pdf", { type: "application/pdf" });
    const reference = new File(["reference bytes"], "reference.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const ignored = new File(["ignored bytes"], "ignored.pdf", { type: "application/pdf" });
    const entries: InventoryEntry[] = [
      {
        clientFileId: "client-source",
        file: source,
        relativePath: "pack/statements/statement.pdf",
        filename: "statement.pdf",
        sizeBytes: source.size,
        contentType: source.type,
        status: "SUPPORTED",
        reason: "Supported source document.",
        selected: true,
        purpose: "SOURCE",
      },
      {
        clientFileId: "client-reference",
        file: reference,
        relativePath: "pack/reference/reference.xlsx",
        filename: "reference.xlsx",
        sizeBytes: reference.size,
        contentType: reference.type,
        status: "SUPPORTED",
        reason: "Supported reference workbook.",
        selected: true,
        purpose: "REFERENCE",
      },
      {
        clientFileId: "client-ignored",
        file: ignored,
        relativePath: "pack/ignored.pdf",
        filename: "ignored.pdf",
        sizeBytes: ignored.size,
        contentType: ignored.type,
        status: "SUPPORTED",
        reason: "Manually deselected.",
        selected: false,
        purpose: "SOURCE",
      },
    ];
    let capturedBody: FormData | undefined;
    let capturedKey: string | null = null;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      expect(String(input)).toBe("https://review.test/api/ui/v1/jobs");
      expect(init?.method).toBe("POST");
      capturedBody = init?.body as FormData;
      capturedKey = new Headers(init?.headers).get("Idempotency-Key");
      return Response.json(startFixture, { status: 202 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await new HttpWorkspaceAdapter("https://review.test").startJob({
      profileId: "journal-entries",
      caseName: "September statements",
      entries,
      idempotencyKey: "idempotency-abc",
    });

    expect(response).toEqual(startFixture);
    expect(capturedKey).toBe("idempotency-abc");
    expect(capturedBody).toBeInstanceOf(FormData);
    const manifest = JSON.parse(String(capturedBody?.get("manifest")));
    expect(manifest).toEqual({
      profile_id: "journal-entries",
      case_name: "September statements",
      files: [{
        client_file_id: "client-source",
        relative_path: "pack/statements/statement.pdf",
        filename: "statement.pdf",
        size_bytes: source.size,
        content_type: "application/pdf",
        selection_status: "SELECTED",
        purpose: "SOURCE",
      }, {
        client_file_id: "client-reference",
        relative_path: "pack/reference/reference.xlsx",
        filename: "reference.xlsx",
        size_bytes: reference.size,
        content_type: reference.type,
        selection_status: "SELECTED",
        purpose: "REFERENCE",
      }],
    });
    const files = capturedBody?.getAll("files") as File[];
    expect(files.map((file) => file.name)).toEqual(["statement.pdf", "reference.xlsx"]);
    expect(await files[0].text()).toBe("source bytes");
    expect(await files[1].text()).toBe("reference bytes");
  });

  it("normalizes an empty browser MIME to the manifest type without changing the uploaded bytes", async () => {
    const source = new File(["exact typeless bytes"], "statement.pdf");
    const entry: InventoryEntry = {
      clientFileId: "client-typeless",
      file: source,
      relativePath: "pack/statement.pdf",
      filename: "statement.pdf",
      sizeBytes: source.size,
      contentType: "application/pdf",
      status: "SUPPORTED",
      reason: "Supported source document.",
      selected: true,
      purpose: "SOURCE",
    };
    let capturedBody: FormData | undefined;
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (_input, init) => {
      capturedBody = init?.body as FormData;
      return Response.json({ ...startFixture, case_name: "Typeless browser file" }, { status: 202 });
    }));

    await new HttpWorkspaceAdapter("https://review.test").startJob({
      profileId: "journal-entries",
      caseName: "Typeless browser file",
      entries: [entry],
      idempotencyKey: "typeless-key",
    });

    const manifest = JSON.parse(String(capturedBody?.get("manifest")));
    const [uploaded] = capturedBody?.getAll("files") as File[];
    expect(manifest.files[0].content_type).toBe("application/pdf");
    expect(uploaded.type).toBe("application/pdf");
    expect(await uploaded.text()).toBe("exact typeless bytes");
  });

  it("will not construct a request for an empty or unreadable selected manifest", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    const adapter = new HttpWorkspaceAdapter("https://review.test");

    await expect(adapter.startJob({
      profileId: "journal-entries",
      caseName: "Empty",
      entries: [],
      idempotencyKey: "empty-key",
    })).rejects.toThrow("Select at least one source file");

    await expect(adapter.startJob({
      profileId: "journal-entries",
      caseName: "Unreadable",
      idempotencyKey: "unreadable-key",
      entries: [{
        clientFileId: "unreadable",
        relativePath: "pack/unreadable.pdf",
        filename: "unreadable.pdf",
        sizeBytes: 10,
        contentType: "application/pdf",
        status: "UNREADABLE",
        reason: "Permission denied",
        selected: true,
        purpose: "SOURCE",
      }],
    })).rejects.toThrow("cannot be uploaded");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports measured XHR upload progress separately from backend processing", async () => {
    class FakeUploadRequest extends EventTarget {
      static latest: FakeUploadRequest | undefined;
      readonly upload = new EventTarget();
      status = 202;
      responseText = JSON.stringify({ ...startFixture, case_name: "Measured upload" });
      open = vi.fn();
      setRequestHeader = vi.fn();
      constructor() {
        super();
        FakeUploadRequest.latest = this;
      }
      send = vi.fn(() => {
        this.upload.dispatchEvent(new ProgressEvent("progress", {
          lengthComputable: true,
          loaded: 45,
          total: 90,
        }));
        this.dispatchEvent(new Event("load"));
      });
    }
    vi.stubGlobal("XMLHttpRequest", FakeUploadRequest);
    const onUploadProgress = vi.fn();

    const result = await new HttpWorkspaceAdapter("https://review.test").startJob({
      profileId: "journal-entries",
      caseName: "Measured upload",
      entries: [sourceEntry()],
      idempotencyKey: "measured-upload-key",
      onUploadProgress,
    });

    expect(result).toEqual({ ...startFixture, case_name: "Measured upload" });
    const request = FakeUploadRequest.latest;
    expect(request?.open).toHaveBeenCalledWith("POST", "https://review.test/api/ui/v1/jobs");
    expect(request?.setRequestHeader).toHaveBeenCalledWith("Idempotency-Key", "measured-upload-key");
    expect(onUploadProgress).toHaveBeenNthCalledWith(1, {
      loadedBytes: 45,
      totalBytes: 90,
      percentage: 50,
    });
    expect(onUploadProgress).toHaveBeenLastCalledWith({
      loadedBytes: 90,
      totalBytes: 90,
      percentage: 100,
    });
  });

  it("preserves the bridge's structured rejection code and actionable message", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json({
      detail: {
        code: "INVALID_FILE_SIGNATURE",
        message: "statement.pdf is not a PDF",
      },
    }, { status: 415 })));

    await expect(new HttpWorkspaceAdapter("https://review.test").startJob({
      profileId: "journal-entries",
      caseName: "Rejected upload",
      entries: [sourceEntry()],
      idempotencyKey: "rejected-upload-key",
    })).rejects.toThrow("INVALID_FILE_SIGNATURE: statement.pdf is not a PDF");
  });

  it("retains definitive missing-job status and scopes remembered jobs to the configured backend", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json({
      detail: { code: "JOB_NOT_FOUND", message: "no such job" },
    }, { status: 404 })));
    const first = new HttpWorkspaceAdapter("http://127.0.0.1:8030");
    const second = new HttpWorkspaceAdapter("http://127.0.0.1:8040");
    expect(first.sessionKey).not.toBe(second.sessionKey);
    expect(first.sessionKey).toBe(new HttpWorkspaceAdapter("http://127.0.0.1:8030/").sessionKey);
    await expect(first.getJob("missing")).rejects.toMatchObject({ status: 404, code: "JOB_NOT_FOUND" });
  });

  it.each([null, { document_id: null, extraction_status: "FAILED", warnings: ["Unreadable PDF"] }])(
    "accepts unavailable ATLAS metadata on a failed source so the result remains inspectable: %s",
    async (atlas) => {
      const payload = {
        ...resultFixture,
        processing_state: "FAILED",
        documents: [{
          ...resultFixture.documents[0],
          atlas,
          processing_state: "FAILED",
          computational_outcome: null,
          error: "Unreadable PDF",
          statement: undefined,
          rows: [],
          transaction_links: [],
          checks: [],
        }],
      };
      vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json(payload)));
      const result = await new HttpWorkspaceAdapter().getResult("job-123");
      expect(result.documents[0].error).toBe("Unreadable PDF");
    },
  );

  it("validates start, status, result and review responses before exposing them to the UI", async () => {
    const adapter = new HttpWorkspaceAdapter("https://review.test");
    const source = new File(["source"], "statement.pdf", { type: "application/pdf" });
    const entry: InventoryEntry = {
      clientFileId: "source",
      file: source,
      relativePath: "statement.pdf",
      filename: "statement.pdf",
      sizeBytes: source.size,
      contentType: source.type,
      status: "SUPPORTED",
      reason: "Supported source document.",
      selected: true,
      purpose: "SOURCE",
    };
    const responses: unknown[] = [
      { ...startFixture, idempotency_reused: undefined },
      { ...completedJobFixture, documents: "not-an-array" },
      { ...resultFixture, findings: "not-an-array" },
      { job_id: "job-123", finding_id: "finding-link-1", status: "CHANGED", review_status: "REVIEWED", updated_at: "now" },
    ];
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json(responses.shift())));

    await expect(adapter.startJob({
      profileId: "journal-entries",
      caseName: "Test",
      entries: [entry],
      idempotencyKey: "key",
    })).rejects.toThrow("job-start response is incompatible");
    await expect(adapter.getJob("job-123")).rejects.toThrow("job-status response is incompatible");
    await expect(adapter.getResult("job-123")).rejects.toThrow("result response is incompatible");
    await expect(adapter.updateFindingReview("job-123", "finding-link-1", "REVIEWED"))
      .rejects.toThrow("human-review response is incompatible");
  });

  it("rejects a job-start response for a different requested profile or case", async () => {
    const adapter = new HttpWorkspaceAdapter("https://review.test");
    const responses = [
      { ...startFixture, profile_id: "pipeline-validation" },
      { ...startFixture, case_name: "Another case" },
    ];
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json(responses.shift())));

    const request = {
      profileId: "journal-entries",
      caseName: "September statements",
      entries: [sourceEntry()],
      idempotencyKey: "identity-key",
    };
    await expect(adapter.startJob(request)).rejects.toThrow("job-start response is incompatible");
    await expect(adapter.startJob({ ...request, idempotencyKey: "identity-key-2" }))
      .rejects.toThrow("job-start response is incompatible");
  });

  it("rejects job, result, review and replay payloads for different requested identities", async () => {
    const adapter = new HttpWorkspaceAdapter("https://review.test");
    const responses: unknown[] = [
      { ...completedJobFixture, job_id: "job-other" },
      { ...resultFixture, job_id: "job-other" },
      {
        job_id: "job-other",
        finding_id: "finding-link-1",
        status: "FAIL",
        review_status: "REVIEWED",
        updated_at: "now",
      },
      {
        job_id: "job-123",
        finding_id: "finding-other",
        status: "FAIL",
        review_status: "REVIEWED",
        updated_at: "now",
      },
      { ...replayFixture, replay_id: "replay-other" },
    ];
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json(responses.shift())));

    await expect(adapter.getJob("job-123")).rejects.toThrow("job-status response is incompatible");
    await expect(adapter.getResult("job-123")).rejects.toThrow("result response is incompatible");
    await expect(adapter.updateFindingReview("job-123", "finding-link-1", "REVIEWED"))
      .rejects.toThrow("human-review response is incompatible");
    await expect(adapter.updateFindingReview("job-123", "finding-link-1", "REVIEWED"))
      .rejects.toThrow("human-review response is incompatible");
    await expect(adapter.getReplay("replay-batch-7"))
      .rejects.toThrow("recorded-run response is incompatible");
  });

  it("uses encoded source/artifact paths and terminal-state recognition", () => {
    const adapter = new HttpWorkspaceAdapter("https://review.test/");
    expect(adapter.sourceUrl("job /1", "source/1")).toBe(
      "https://review.test/api/ui/v1/jobs/job%20%2F1/sources/source%2F1",
    );
    expect(adapter.artifactUrl("job /1", "result/json")).toBe(
      "https://review.test/api/ui/v1/jobs/job%20%2F1/artifacts/result%2Fjson",
    );
    expect(isTerminalJob("SUCCEEDED")).toBe(true);
    expect(isTerminalJob("PARTIAL")).toBe(true);
    expect(isTerminalJob("FAILED")).toBe(true);
    expect(isTerminalJob("PROCESSING")).toBe(false);
  });
});
