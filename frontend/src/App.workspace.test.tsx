import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { App } from "./App";
import { MockReviewAdapter } from "./api/mockReviewAdapter";
import { makeAdapter, startFixture } from "./test/workspaceFixtures";
import type { EmailDraft, ExportResult, ReviewProgress } from "./types";
import type { WorkspaceAdapter } from "./workspaceTypes";

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
  it("keeps Full pack disabled and falls back to the Profile landing when its flag is off", async () => {
    window.history.replaceState({}, "", "/?workspace=pack");
    render(<App adapter={new ImmediateAdapter()} profileAdapter={makeAdapter()} />);
    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Review workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Profile workflows" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Full pack" })).not.toBeInTheDocument();
    expect(document.title).toBe("CrazyMonkey — Profile workflows");
  });

  it("uses the folder review as the root landing action", async () => {
    window.history.replaceState({}, "", "/");
    render(<App adapter={new ImmediateAdapter()} profileAdapter={makeAdapter()} />);

    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Profile workflows" })).toHaveAttribute("aria-pressed", "true");
    expect(document.title).toBe("CrazyMonkey — Profile workflows");
  });

  it("opens Profile workflows from its URL and keeps NAV reachable", async () => {
    window.history.replaceState({}, "", "/?workspace=profiles");
    const user = userEvent.setup();
    render(<App adapter={new ImmediateAdapter()} profileAdapter={makeAdapter()} />);

    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Profile workflows" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Profile API workspace")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Full pack" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "NAV review" }));
    expect(screen.getByRole("heading", { name: "Review your NAV pack before you sign it." })).toBeInTheDocument();
    expect(screen.getByText("Development fixture mode")).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get("workspace")).toBe("nav");
    expect(document.title).toBe("CrazyMonkey — NAV review");

    act(() => {
      window.history.replaceState({}, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Profile workflows" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps an accepted Profile job mounted while another workspace is viewed", async () => {
    window.history.replaceState({}, "", "/?workspace=profiles");
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>(() => new Promise(() => undefined));
    render(
      <App
        adapter={new ImmediateAdapter()}
        profileAdapter={makeAdapter({ startJob, getJob })}
      />,
    );

    const file = new File(["statement bytes"], "statement.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText("Choose files"), file);
    await user.click(screen.getByRole("checkbox", {
      name: "I confirm these are the intended source and reference inputs.",
    }));
    await user.click(screen.getByRole("button", { name: "Start review" }));
    expect(await screen.findByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "NAV review" }));
    expect(screen.getByRole("heading", { name: "Review your NAV pack before you sign it." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Profile workflows" }));

    expect(screen.getByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();
    expect(startJob).toHaveBeenCalledTimes(1);
  });

  it("does not steal Profile input focus when a hidden NAV review completes", async () => {
    window.history.replaceState({}, "", "/?workspace=nav");
    const user = userEvent.setup();
    const adapter = new MockReviewAdapter();
    let resolveProgress!: (progress: ReviewProgress) => void;
    vi.spyOn(adapter, "getProgress").mockImplementation(() => new Promise((resolve) => {
      resolveProgress = resolve;
    }));
    const getReview = vi.spyOn(adapter, "getReview");
    render(<App adapter={adapter} profileAdapter={makeAdapter()} />);

    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    expect(await screen.findByRole("heading", { name: "Reviewing the evidence" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Profile workflows" }));
    const caseName = await screen.findByRole("textbox", { name: "Case / folder name" });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Drop a folder to start a review" })).toHaveFocus());
    await user.click(caseName);
    expect(caseName).toHaveFocus();

    await act(async () => resolveProgress({ reviewId: "background-nav", state: "COMPLETE", stages: [], messages: [] }));
    await waitFor(() => expect(getReview).toHaveBeenCalled());
    expect(caseName).toHaveFocus();
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
    window.history.replaceState({}, "", "/?workspace=nav");
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
    window.history.replaceState({}, "", "/?workspace=nav");
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
