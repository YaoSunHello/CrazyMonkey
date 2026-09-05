import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { ProfileWorkspace } from "./ProfileWorkspace";
import { WorkspaceRequestError } from "./api/workspaceAdapter";
import { completedJobFixture, makeAdapter, replayFixture, resultFixture, startFixture } from "./test/workspaceFixtures";
import type { WorkspaceAdapter } from "./workspaceTypes";

afterEach(() => window.sessionStorage.clear());

async function prepareManifest(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(
    await screen.findByLabelText("Choose files"),
    new File(["statement bytes"], "statement.pdf", { type: "application/pdf" }),
  );
}

describe("workspace resilience and truth labels", () => {
  it("uses a fresh submission identity after explicitly choosing New review", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    render(<ProfileWorkspace adapter={makeAdapter({
      startJob,
      getJob: async () => completedJobFixture,
      getResult: async () => resultFixture,
    })} />);
    await prepareManifest(user);
    await user.click(screen.getByRole("button", { name: "Start review" }));
    await user.click(await screen.findByRole("button", { name: "← New review" }));
    await user.click(screen.getByRole("button", { name: "Start review" }));
    await waitFor(() => expect(startJob).toHaveBeenCalledTimes(2));
    expect(startJob.mock.calls[1][0].idempotencyKey).not.toBe(startJob.mock.calls[0][0].idempotencyKey);
  });

  it.each([
    new WorkspaceRequestError("JOB_NOT_FOUND: no such job", 404, "JOB_NOT_FOUND"),
    new WorkspaceRequestError("Request failed (404).", 404),
  ])("returns an unavailable accepted job to its selected inventory instead of polling forever: %s", async (error) => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>()
      .mockRejectedValueOnce(error)
      .mockImplementation(() => new Promise(() => undefined));
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob })} />);
    await prepareManifest(user);
    await user.click(screen.getByRole("button", { name: "Start review" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Your selected files are still here");
    expect(screen.getByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start review" })).toBeEnabled();
    expect(getJob).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Start review" }));
    expect(startJob).toHaveBeenCalledTimes(2);
    expect(startJob.mock.calls[1][0].idempotencyKey).not.toBe(startJob.mock.calls[0][0].idempotencyKey);
  });

  it("restores an accepted job after remount and preserves its final backend trace without another upload", async () => {
    const user = userEvent.setup();
    const sessionKey = "test.ui.v1.job:backend-a";
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>()
      .mockImplementationOnce(() => new Promise(() => undefined))
      .mockResolvedValue(completedJobFixture);
    const adapter = makeAdapter({ sessionKey, startJob, getJob, getResult: async () => resultFixture });
    const firstMount = render(<ProfileWorkspace adapter={adapter} />);
    await prepareManifest(user);
    await user.click(screen.getByRole("button", { name: "Start review" }));
    expect(await screen.findByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem(sessionKey)!)).toEqual(startFixture);
    firstMount.unmount();

    render(<ProfileWorkspace adapter={adapter} />);
    expect(await screen.findByRole("heading", { name: "Show the arithmetic" })).toBeInTheDocument();
    await user.click(screen.getByText("Processing history (2 events)"));
    expect(screen.getByRole("list", { name: "Actual processing history" })).toHaveTextContent("Deterministic verification complete");
    expect(startJob).toHaveBeenCalledTimes(1);
    expect(getJob).toHaveBeenNthCalledWith(2, "job-123");
    await user.click(screen.getByRole("button", { name: "← New review" }));
    expect(window.sessionStorage.getItem(sessionKey)).toBeNull();
  });

  it("clears a saved job that disappeared after a backend restart and requests the original files again", async () => {
    const sessionKey = "test.ui.v1.job:restarted-backend";
    window.sessionStorage.setItem(sessionKey, JSON.stringify(startFixture));
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>();
    render(<ProfileWorkspace adapter={makeAdapter({
      sessionKey,
      startJob,
      getJob: async () => { throw new WorkspaceRequestError("no such job", 404, "JOB_NOT_FOUND"); },
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose the original files again");
    expect(window.sessionStorage.getItem(sessionKey)).toBeNull();
    expect(startJob).not.toHaveBeenCalled();
  });

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
