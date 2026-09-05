import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpReviewAdapter } from "./httpReviewAdapter";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("HttpReviewAdapter", () => {
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
});
