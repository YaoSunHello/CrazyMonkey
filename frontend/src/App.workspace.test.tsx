import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { App } from "./App";
import { MockReviewAdapter } from "./api/mockReviewAdapter";
import type { EmailDraft, ExportResult, ReviewProgress } from "./types";

class ImmediateAdapter extends MockReviewAdapter {
  override async getProgress(reviewId: string): Promise<ReviewProgress> {
    return { reviewId, state: "COMPLETE", stages: [], messages: [] };
  }
}

class RelayReadyAdapter extends ImmediateAdapter {
  override async getReview(reviewId: string) {
    const review = await super.getReview(reviewId);
    return {
      ...review,
      findings: review.findings.map((finding) =>
        finding.status === "MATCH" ? finding : { ...finding, humanReviewState: "REVIEWED" as const },
      ),
    };
  }
}

function serveEmptyPackWorkspace() {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    if (String(url).endsWith("/api/pack/config")) return Response.json({ configured: false, provider: null, model: null });
    if (String(url).endsWith("/api/pack/runs")) return Response.json({ runs: [] });
    throw new Error("Unexpected request in mocked workspace test");
  }));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.history.replaceState({}, "", "/");
});

describe("Workspace isolation", () => {
  it("keeps Full pack disabled by default even with a Full pack URL", async () => {
    window.history.replaceState({}, "", "/?workspace=pack");
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<App adapter={new ImmediateAdapter()} />);
    expect(screen.getByText("Development fixture mode")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Review your NAV pack before you sign it." })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Review workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Full pack" })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    expect(await screen.findByRole("heading", { name: "Review summary" })).toBeInTheDocument();
    expect(screen.getByText("Development fixture mode")).toBeInTheDocument();
  });

  it("opens Full pack from the URL only when the frontend feature flag is enabled", async () => {
    vi.stubEnv("VITE_ENABLE_PACK_WORKSPACE", "1");
    window.history.replaceState({}, "", "/?workspace=pack");
    serveEmptyPackWorkspace();
    render(<App adapter={new ImmediateAdapter()} />);
    expect(await screen.findByRole("heading", { name: "Bring the whole dataset." })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Review workspace" })).toBeInTheDocument();
    expect(screen.getByText("Pack API workspace")).toBeInTheDocument();
    expect(screen.queryByText(/Gemini|live-model/i)).not.toBeInTheDocument();
  });

  it("keeps a late NAV email response out of Full pack and preserves it when returning to NAV", async () => {
    vi.stubEnv("VITE_ENABLE_PACK_WORKSPACE", "1");
    serveEmptyPackWorkspace();
    const user = userEvent.setup();
    const adapter = new RelayReadyAdapter();
    let resolveEmail!: (draft: EmailDraft) => void;
    vi.spyOn(adapter, "prepareEmail").mockImplementation(() => new Promise(resolve => { resolveEmail = resolve; }));
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await screen.findByRole("heading", { name: "Review summary" });
    await user.click(screen.getByRole("button", { name: "Prepare email" }));
    await user.click(screen.getByRole("button", { name: "Full pack" }));
    expect(screen.getByRole("heading", { name: "Bring the whole dataset." })).toBeInTheDocument();
    await act(async () => resolveEmail({
      id: "late-nav-draft", status: "DRAFT", recipient: "", subject: "NAV-only draft", body: "Saved NAV preview", attachments: [],
    }));
    expect(screen.queryByRole("dialog", { name: "Email preview" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "NAV review" }));
    expect(await screen.findByRole("dialog", { name: "Email preview" })).toBeInTheDocument();
    expect(screen.getByText("NAV-only draft")).toBeInTheDocument();
  });

  it("keeps a late NAV export notification out of Full pack", async () => {
    vi.stubEnv("VITE_ENABLE_PACK_WORKSPACE", "1");
    serveEmptyPackWorkspace();
    const user = userEvent.setup();
    const adapter = new RelayReadyAdapter();
    let resolveExport!: (result: ExportResult) => void;
    vi.spyOn(adapter, "requestExport").mockImplementation(() => new Promise(resolve => { resolveExport = resolve; }));
    render(<App adapter={adapter} />);
    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    await screen.findByRole("heading", { name: "Review summary" });
    await user.click(screen.getByRole("button", { name: "JSON audit package" }));
    await user.click(screen.getByRole("button", { name: "Full pack" }));
    await act(async () => resolveExport({ available: false, message: "NAV export unavailable for this snapshot." }));
    expect(screen.queryByText("NAV export unavailable for this snapshot.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "NAV review" }));
    expect(screen.getByText("NAV export unavailable for this snapshot.")).toBeInTheDocument();
  });
});
