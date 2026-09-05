import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { App } from "./App";
import { HttpReviewAdapter } from "./api/httpReviewAdapter";
import { MockReviewAdapter } from "./api/mockReviewAdapter";
import { syntheticReviewFixture } from "./data/syntheticReview";
import type { HumanReviewUpdate, ReviewProgress, ReviewResult } from "./types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function serveReview(options: { termCorrection?: boolean; failRefresh?: boolean; mode?: ReviewResult["mode"] } = {}) {
  const snapshot = structuredClone(syntheticReviewFixture);
  const readVersions: number[] = [];
  Object.assign(snapshot.outputCapabilities, { termCorrection: options.termCorrection ?? false });
  snapshot.source = "ATLAS";
  snapshot.mode = options.mode ?? "SYNTHETIC_DEMO";
  snapshot.sourceNotice = "Original files were normalized by ATLAS and processed by the runtime.";

  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input)).pathname;
    if (path === "/api/v1/demo/reviews" && init?.method === "POST") {
      return Response.json({ reviewId: snapshot.id });
    }
    if (path === `/api/v1/reviews/${snapshot.id}/progress`) {
      return Response.json({ reviewId: snapshot.id, state: "COMPLETE", stages: [], messages: [] });
    }
    if (path === `/api/v1/reviews/${snapshot.id}`) {
      readVersions.push(snapshot.version);
      if (options.failRefresh && snapshot.version > 1) {
        return Response.json({ detail: "Review refresh temporarily unavailable." }, { status: 503 });
      }
      return Response.json(snapshot);
    }
    if (init?.method === "PATCH" && path.endsWith("/review")) {
      const finding = snapshot.findings.find((item) => path.includes(`/findings/${item.id}/`));
      if (!finding) return Response.json({ detail: "Finding not found" }, { status: 404 });
      const update = JSON.parse(String(init.body)) as HumanReviewUpdate;
      snapshot.version += 1;
      finding.humanReviewState = update.state;
      snapshot.findings.forEach((item) => {
        item.versions = [{
          version: snapshot.version,
          createdAt: "2026-09-05T14:00:00Z",
          reason: "Current immutable review snapshot",
        }];
      });
      return Response.json(finding);
    }
    throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { adapter: new HttpReviewAdapter("http://review.test"), fetchMock, readVersions, snapshot };
}

describe("BEACON runtime integration", () => {
  it("reloads the complete immutable snapshot after human review, preserving the financial result", async () => {
    const user = userEvent.setup();
    const { adapter, readVersions, snapshot } = serveReview();
    snapshot.findings.forEach((finding) => {
      if (finding.status !== "MATCH" && finding.investorId !== "LP03") {
        finding.humanReviewState = "REVIEWED";
      }
    });
    const requestExport = vi.spyOn(adapter, "requestExport").mockResolvedValue({ available: false });
    const prepareEmail = vi.spyOn(adapter, "prepareEmail").mockResolvedValue({
      id: "version-2-draft",
      status: "DRAFT",
      recipient: "",
      subject: "Version 2 review",
      body: "Draft only",
      attachments: [],
      reviewVersion: 2,
      snapshotSha256: "a".repeat(64),
    });
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review LP03 Management fee finding" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /LP03.*Management fee/ })).toHaveFocus());
    await user.type(screen.getByLabelText(/Reviewer display name/), "Integration reviewer");
    await user.click(screen.getByRole("button", { name: "Mark reviewed" }));

    await waitFor(() => expect(screen.getAllByText("Reviewed").length).toBeGreaterThan(0));
    expect(readVersions).toEqual([1, 2]);
    const versions = screen.getByRole("region", { name: "Review versions" });
    expect(within(versions).getByText("Version 2")).toBeInTheDocument();
    expect(screen.getByText("£12,500 above reconstruction")).toBeInTheDocument();
    expect(screen.getAllByText("Discrepancy").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Back to findings" }));
    await user.click(screen.getByRole("button", { name: "Review LP04 Management fee finding" }));
    expect(within(screen.getByRole("region", { name: "Review versions" })).getByText("Version 2")).toBeInTheDocument();

    // Another client can advance the server without changing this displayed snapshot.
    snapshot.version = 3;
    await user.click(screen.getByRole("button", { name: "Back to findings" }));
    await user.click(screen.getByRole("button", { name: "JSON audit package" }));
    expect(requestExport).toHaveBeenCalledWith(snapshot.id, "json", 2);
    await user.click(screen.getByRole("button", { name: "Prepare email" }));
    expect(prepareEmail).toHaveBeenCalledWith(snapshot.id, 2);
    expect(await screen.findByRole("dialog", { name: "Email preview" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm and send" })).not.toBeInTheDocument();
  });

  it.each([
    ["SYNTHETIC_DEMO", "Synthetic source review"],
    ["LIVE_OFFLINE", "Offline source review"],
    ["LIVE_MODEL", "Model-assisted source review"],
  ] as const)("shows the ATLAS source notice and honest label for %s", async (mode, label) => {
    const user = userEvent.setup();
    const { adapter, snapshot } = serveReview({ mode });
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    const provenance = await screen.findByRole("region", { name: "Review provenance" });
    expect(provenance).toHaveTextContent(label);
    expect(within(provenance).getByText(snapshot.sourceNotice!)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review next exception" }));
    expect(await screen.findByText(
      mode === "LIVE_MODEL"
        ? "Agent commentary"
        : mode === "SYNTHETIC_DEMO"
          ? "Deterministic challenger commentary"
          : "Offline challenger commentary",
    )).toBeInTheDocument();
  });

  it.each(["Mark reviewed", "Add note"])("reports a saved %s action honestly when the subsequent refresh fails", async (button) => {
    const user = userEvent.setup();
    const { adapter, readVersions } = serveReview({ failRefresh: true });
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review LP03 Management fee finding" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /LP03.*Management fee/ })).toHaveFocus());
    await user.type(screen.getByLabelText(/Reviewer display name/), "Integration reviewer");
    await user.type(screen.getByLabelText("Review note"), "Source checked; follow-up still required.");
    await user.click(screen.getByRole("button", { name: button }));

    const alerts = await screen.findAllByRole("alert");
    expect(readVersions).toEqual([1, 2]);
    alerts.forEach((alert) => expect(alert).toHaveTextContent(
      "Review action was saved, but the updated review could not be loaded.",
    ));
    expect(screen.queryByText(/was not saved|could not be saved/)).not.toBeInTheDocument();
  });

  it("disables correction when the runtime explicitly reports that it is unsupported", async () => {
    const user = userEvent.setup();
    const { adapter, fetchMock } = serveReview();
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review LP03 Management fee finding" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /LP03.*Management fee/ })).toHaveFocus());
    await user.type(screen.getByLabelText(/Reviewer display name/), "Integration reviewer");

    const correction = screen.getByRole("button", { name: "Correct term" });
    expect(correction).toBeDisabled();
    await user.click(correction);
    expect(screen.queryByRole("dialog", { name: "Correct extracted term" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/corrections"))).toBe(false);
  });

  it("does not allow a missing-evidence finding to be marked term confirmed", async () => {
    const user = userEvent.setup();
    const { adapter } = serveReview();
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review LP06 Management fee finding" }));

    expect(await screen.findByRole("button", { name: "Confirm term" })).toBeDisabled();
    expect(screen.getByText(/Term confirmation is unavailable until source evidence/i)).toBeInTheDocument();
  });

  it.each([
    ["a mismatched version", 2, "a".repeat(64), /draft snapshot v2/],
    ["a missing hash", 1, undefined, /did not return the immutable review version and snapshot hash/],
  ] as const)("refuses an email draft with %s", async (_case, reviewVersion, snapshotSha256, errorText) => {
    const user = userEvent.setup();
    const { adapter, snapshot } = serveReview();
    snapshot.findings.forEach((finding) => {
      if (finding.status !== "MATCH") finding.humanReviewState = "REVIEWED";
    });
    vi.spyOn(adapter, "prepareEmail").mockResolvedValue({
      id: "wrong-draft",
      status: "DRAFT",
      recipient: "",
      subject: "Review draft",
      body: "Draft only",
      attachments: [],
      reviewVersion,
      snapshotSha256,
    });
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Prepare email" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(errorText);
    expect(screen.queryByRole("dialog", { name: "Email preview" })).not.toBeInTheDocument();
  });

  it("preserves fixture correction when the optional capability is absent", async () => {
    class ImmediateMockReviewAdapter extends MockReviewAdapter {
      override async getProgress(reviewId: string): Promise<ReviewProgress> {
        return { reviewId, state: "COMPLETE", stages: [], messages: [] };
      }
    }
    const user = userEvent.setup();
    render(<App adapter={new ImmediateMockReviewAdapter()} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await user.click(await screen.findByRole("button", { name: "Review LP03 Management fee finding" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /LP03.*Management fee/ })).toHaveFocus());
    await user.type(screen.getByLabelText(/Reviewer display name/), "Fixture reviewer");
    await user.click(screen.getByRole("button", { name: "Correct term" }));
    expect(await screen.findByRole("dialog", { name: "Correct extracted term" })).toBeInTheDocument();
  });
});
