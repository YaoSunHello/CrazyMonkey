import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ProfileWorkspace } from "./ProfileWorkspace";
import { makeAdapter, replayFixture, startFixture } from "./test/workspaceFixtures";
import type { WorkspaceAdapter } from "./workspaceTypes";

async function prepareManifest(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(
    await screen.findByLabelText("Choose files"),
    new File(["statement bytes"], "statement.pdf", { type: "application/pdf" }),
  );
  await user.click(screen.getByRole("checkbox", {
    name: "I confirm these are the intended source and reference inputs.",
  }));
}

describe("workspace resilience and truth labels", () => {
  it("reuses the idempotency key when the identical manifest is retried after an uncertain start failure", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>()
      .mockRejectedValueOnce(new Error("response lost after upload"))
      .mockResolvedValueOnce({ ...startFixture, idempotency_reused: true });
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>(() => new Promise(() => undefined));
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob })} />);
    await prepareManifest(user);

    await user.click(screen.getByRole("button", { name: "Start review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Review was not started. response lost after upload");
    await user.click(screen.getByRole("button", { name: "Start review" }));

    expect(await screen.findByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();
    expect(startJob).toHaveBeenCalledTimes(2);
    expect(startJob.mock.calls[0][0].idempotencyKey).toBe(startJob.mock.calls[1][0].idempotencyKey);
    expect(screen.getByRole("status")).toHaveTextContent(
      "The backend reused the existing idempotent job; no duplicate processing was launched.",
    );
  });

  it("labels committed playback as RECORDED REPLAY and makes no processing request", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>();
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>();
    const getResult = vi.fn<WorkspaceAdapter["getResult"]>();
    const getReplay = vi.fn<WorkspaceAdapter["getReplay"]>().mockResolvedValue(replayFixture);
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob, getResult, getReplay })} />);

    await user.click(await screen.findByRole("button", { name: "Open recorded run" }));

    expect(await screen.findByRole("heading", { name: "Journal entry validation" })).toBeInTheDocument();
    expect(screen.getAllByText("RECORDED REPLAY").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("This is playback, not a rerun.")).toBeInTheDocument();
    expect(screen.getByText(/Model calls: 0\. Event trace available: no\. Idle-time compression performed: no\./)).toBeInTheDocument();
    expect(screen.getByText("Original source unavailable in replay")).toBeDisabled();
    expect(startJob).not.toHaveBeenCalled();
    expect(getJob).not.toHaveBeenCalled();
    expect(getResult).not.toHaveBeenCalled();
    expect(getReplay).toHaveBeenCalledWith("replay-batch-7");
  });
});
