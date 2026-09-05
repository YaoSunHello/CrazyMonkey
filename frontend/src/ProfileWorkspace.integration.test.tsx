import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { ProfileWorkspace } from "./ProfileWorkspace";
import {
  completedJobFixture,
  makeAdapter,
  resultFixture,
  startFixture,
} from "./test/workspaceFixtures";
import type { WorkspaceAdapter } from "./workspaceTypes";

afterEach(() => {
  vi.restoreAllMocks();
});

async function selectConfirmAndStart(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(
    await screen.findByLabelText("Choose files"),
    new File(["statement bytes"], "statement.pdf", { type: "application/pdf" }),
  );
  await user.click(screen.getByRole("checkbox", {
    name: "I confirm these are the intended source and reference inputs.",
  }));
  await user.click(screen.getByRole("button", { name: "Start review" }));
}

describe("live processing integration", () => {
  it("reconnects polling to the existing job without issuing another start request", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>()
      .mockRejectedValueOnce(new Error("socket closed"))
      .mockResolvedValueOnce(completedJobFixture);
    const getResult = vi.fn<WorkspaceAdapter["getResult"]>().mockResolvedValue(resultFixture);
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob, getResult })} />);

    await selectConfirmAndStart(user);

    expect(await screen.findByText("Connection interrupted.")).toBeInTheDocument();
    expect(screen.getAllByText("Reconnecting").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Polling will reconnect to this existing job; processing will not restart/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Show the arithmetic" }, { timeout: 4_000 })).toBeInTheDocument();
    expect(startJob).toHaveBeenCalledTimes(1);
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(getResult).toHaveBeenCalledTimes(1);
    expect(getResult).toHaveBeenCalledWith("job-123");
  }, 6_000);

  it("rejects a review response that attempts to mutate the computational outcome", async () => {
    const user = userEvent.setup();
    const updateFindingReview = vi.fn<WorkspaceAdapter["updateFindingReview"]>().mockResolvedValue({
      job_id: "job-123",
      finding_id: "finding-link-1",
      status: "PASS",
      review_status: "REVIEWED",
      updated_at: "2026-09-05T10:01:00Z",
    });
    render(<ProfileWorkspace adapter={makeAdapter({
      getJob: async () => completedJobFixture,
      getResult: async () => resultFixture,
      updateFindingReview,
    })} />);
    await selectConfirmAndStart(user);

    expect(await screen.findByRole("heading", { name: "Show the arithmetic" })).toBeInTheDocument();
    const evidence = screen.getByRole("heading", { name: "Running-balance link" }).closest("aside")!;
    expect(within(evidence).getByText("FAIL", { selector: "dd" })).toBeInTheDocument();
    expect(within(evidence).getByText("UNREVIEWED")).toBeInTheDocument();

    await user.click(within(evidence).getByRole("button", { name: "Mark reviewed" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The server attempted to change the computational outcome while saving a human review state.",
    );
    expect(updateFindingReview).toHaveBeenCalledWith("job-123", "finding-link-1", "REVIEWED");
    expect(within(evidence).getByText("FAIL", { selector: "dd" })).toBeInTheDocument();
    expect(within(evidence).getByText("UNREVIEWED")).toBeInTheDocument();
  });

  it("records a human review state while keeping the FAIL outcome visible", async () => {
    const user = userEvent.setup();
    const updateFindingReview = vi.fn<WorkspaceAdapter["updateFindingReview"]>().mockResolvedValue({
      job_id: "job-123",
      finding_id: "finding-link-1",
      status: "FAIL",
      review_status: "REVIEWED",
      updated_at: "2026-09-05T10:01:00Z",
    });
    render(<ProfileWorkspace adapter={makeAdapter({
      getJob: async () => completedJobFixture,
      getResult: async () => resultFixture,
      updateFindingReview,
    })} />);
    await selectConfirmAndStart(user);
    expect(await screen.findByRole("heading", { name: "Show the arithmetic" })).toBeInTheDocument();

    const evidence = screen.getByRole("heading", { name: "Running-balance link" }).closest("aside")!;
    await user.click(within(evidence).getByRole("button", { name: "Mark reviewed" }));

    expect(await screen.findByRole("status")).toHaveTextContent("REVIEWED recorded. The FAIL check outcome is unchanged.");
    expect(within(evidence).getByText("FAIL", { selector: "dd" })).toBeInTheDocument();
    expect(within(evidence).getByText("REVIEWED")).toBeInTheDocument();
  });
});
