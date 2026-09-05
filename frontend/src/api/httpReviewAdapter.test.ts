import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpReviewAdapter } from "./httpReviewAdapter";
import type { DetectedUpload } from "../types";
import { syntheticReviewFixture } from "../data/syntheticReview";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("HttpReviewAdapter", () => {
  it("posts the original file bytes and matching manifest when starting an uploaded review", async () => {
    const documents: DetectedUpload[] = [
      {
        id: "client-nav",
        filename: "Administrator_NAV.xlsx",
        role: "NAV_WORKBOOK",
        recognition: "RECOGNISED",
        file: new File(["real-workbook-bytes"], "Administrator_NAV.xlsx"),
      },
      {
        id: "client-lpa",
        filename: "Fund_LPA.pdf",
        role: "LPA",
        recognition: "RECOGNISED",
        file: new File(["real-pdf-bytes"], "Fund_LPA.pdf"),
      },
    ];
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ reviewId: "uploaded-review" }, { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(new HttpReviewAdapter("https://review.example/").startReview(documents)).resolves.toEqual({
      reviewId: "uploaded-review",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://review.example/api/v1/reviews",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    const form = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(JSON.parse(String(form.get("manifest")))).toEqual(
      documents.map(({ file: _file, ...document }) => document),
    );
    const postedFiles = form.getAll("files") as File[];
    expect(postedFiles.map((file) => file.name)).toEqual(["Administrator_NAV.xlsx", "Fund_LPA.pdf"]);
    await expect(postedFiles[0].text()).resolves.toBe("real-workbook-bytes");
    await expect(postedFiles[1].text()).resolves.toBe("real-pdf-bytes");
  });

  it("reports an unavailable backend and never substitutes fixture data after a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(new HttpReviewAdapter("https://review.example").getReview("network-failure")).rejects.toThrow(
      "Backend unavailable. Failed to fetch",
    );
  });

  it("prepares an unsent email draft for the explicitly requested review version", async () => {
    const draft = { id: "run-qa-v7-draft", status: "DRAFT", recipient: "", subject: "Version 7", body: "Review draft", attachments: [] };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(Response.json(draft));
    vi.stubGlobal("fetch", fetchMock);

    expect(await new HttpReviewAdapter("https://review.example").prepareEmail("run-qa", 7)).toEqual(draft);
    expect(fetchMock).toHaveBeenCalledWith("https://review.example/api/v1/reviews/run-qa/email/prepare?version=7", { method: "POST" });
  });

  it("downloads the explicitly requested immutable review version and preserves the server filename", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("version-seven-file", {
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="review-v7.xlsx"',
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await new HttpReviewAdapter("https://review.example").requestExport("run-qa", "excel", 7);

    expect(fetchMock).toHaveBeenCalledWith("https://review.example/api/runs/run-qa/versions/7/exports/excel");
    expect(result.available).toBe(true);
    expect(result.filename).toBe("review-v7.xlsx");
    expect(await result.blob?.text()).toBe("version-seven-file");
  });

  it("maps reordered detection results to files using clientFileId", async () => {
    const files = [
      new File(["first"], "Administrator_NAV.xlsx"),
      new File(["second"], "Fund_LPA.pdf"),
    ];
    const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
      const form = init?.body as FormData;
      const clientIds = form.getAll("client_file_ids").map(String);
      return new Response(
        JSON.stringify([
          {
            id: "server-lpa",
            filename: files[1].name,
            role: "LPA",
            recognition: "RECOGNISED",
            clientFileId: clientIds[1],
          },
          {
            id: "server-nav",
            filename: files[0].name,
            role: "NAV_WORKBOOK",
            recognition: "RECOGNISED",
            clientFileId: clientIds[0],
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const detected = await new HttpReviewAdapter("https://review.example").detectDocuments(files);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://review.example/api/v1/documents/detect",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    expect(detected.map((document) => document.filename)).toEqual([
      "Fund_LPA.pdf",
      "Administrator_NAV.xlsx",
    ]);
    expect(detected[0].file).toBe(files[1]);
    expect(detected[1].file).toBe(files[0]);
  });

  it("surfaces FastAPI string and validation-list detail responses", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Synthetic review is disabled." }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: [{ msg: "NAV workbook is required." }, { msg: "LPA is missing." }] }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const adapter = new HttpReviewAdapter("https://review.example");

    await expect(adapter.startSyntheticReview()).rejects.toThrow("Synthetic review is disabled.");
    await expect(adapter.startSyntheticReview()).rejects.toThrow(
      "NAV workbook is required. LPA is missing.",
    );
  });

  it("rejects a raw Atlas snapshot instead of silently falling back to fixture data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ run_id: "raw-atlas", fund_name: "Example Fund", findings: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new HttpReviewAdapter("https://review.example").getReview("raw-atlas")).rejects.toThrow(
      "incompatible BEACON presentation contract",
    );
  });

  it("accepts canonical decimal strings in live money and version fields", async () => {
    const review = structuredClone(syntheticReviewFixture);
    review.source = "ATLAS";
    const finding = review.findings[0];
    finding.administratorValue = { amount: "90071992547409.01", currency: "GBP" };
    finding.expectedValue = { amount: "90071992547400.00", currency: "GBP" };
    finding.difference = { amount: "9.01", currency: "GBP" };
    finding.versions = [{
      version: 1,
      createdAt: review.createdAt,
      reason: "Initial source-linked deterministic review",
      applicableRate: "1.5000",
      expectedValue: structuredClone(finding.expectedValue),
    }];
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(Response.json(review)));

    const result = await new HttpReviewAdapter("https://review.example").getReview(review.id);

    expect(result.findings[0].administratorValue?.amount).toBe("90071992547409.01");
    expect(result.findings[0].versions[0].applicableRate).toBe("1.5000");
  });

  it("rejects non-canonical decimal strings in live money fields", async () => {
    const review = structuredClone(syntheticReviewFixture);
    review.source = "ATLAS";
    review.findings[0].administratorValue = { amount: "9.007199254740901e13", currency: "GBP" };
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(Response.json(review)));

    await expect(new HttpReviewAdapter("https://review.example").getReview(review.id)).rejects.toThrow(
      "incompatible BEACON presentation contract",
    );
  });

  it("rejects a superficially compatible response missing render-critical finding fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(Response.json({
        id: "review-incomplete",
        version: 1,
        mode: "SYNTHETIC_DEMO",
        source: "ATLAS",
        fundName: "Example Fund",
        periodLabel: "Q3 2026",
        createdAt: "2026-09-05T12:00:00Z",
        documents: [],
        findings: [{
          id: "finding-1",
          investorId: "LP01",
          checkName: "Management fee",
          status: "MATCH",
          humanReviewState: "UNREVIEWED",
          explanation: "Values agree.",
          evidence: [],
          checksPerformed: [],
        }],
        outputCapabilities: {
          pdf: true,
          excel: true,
          json: true,
          emailPrepare: true,
          emailSend: false,
        },
      })),
    );

    await expect(
      new HttpReviewAdapter("https://review.example").getReview("review-incomplete"),
    ).rejects.toThrow("incompatible BEACON presentation contract");
  });

  it("preserves RELAY review identity on exports and draft metadata", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response("pdf-bytes", {
          status: 200,
          headers: {
            "Content-Disposition": 'attachment; filename="review-v2.pdf"',
            "X-Review-Version": "2",
            "X-Snapshot-SHA256": "a".repeat(64),
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "draft-2",
            status: "DRAFT",
            recipient: "",
            subject: "Review ready",
            body: "Draft body",
            attachments: ["review-v2.pdf"],
            review_version: 2,
            snapshot_sha256: "a".repeat(64),
            send_instructions: "Preview confirmation is required before sending.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const adapter = new HttpReviewAdapter("https://review.example");

    const exported = await adapter.requestExport("review-2", "pdf", 2);
    expect(exported.filename).toBe("review-v2.pdf");
    expect(exported.reviewVersion).toBe(2);
    expect(exported.snapshotSha256).toBe("a".repeat(64));

    const draft = await adapter.prepareEmail("review-2", 2);
    expect(draft.reviewVersion).toBe(2);
    expect(draft.snapshotSha256).toBe("a".repeat(64));
    expect(draft.sendInstructions).toContain("confirmation");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://review.example/api/runs/review-2/versions/2/exports/pdf",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://review.example/api/v1/reviews/review-2/email/prepare?version=2",
      { method: "POST" },
    );
  });
});
