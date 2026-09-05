import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ProfileWorkspace } from "./ProfileWorkspace";
import { bootstrapFixture, makeAdapter, startFixture } from "./test/workspaceFixtures";
import type { WorkspaceAdapter } from "./workspaceTypes";

async function chooseSource(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(["real uploaded statement bytes"], "statement.pdf", { type: "application/pdf" });
  await user.upload(await screen.findByLabelText("Choose files"), file);
  expect(await screen.findByText("statement.pdf")).toBeInTheDocument();
  return file;
}

describe("CrazyMonkey live workspace", () => {
  it("discovers profiles from the backend and never starts merely because a file was selected", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>(() => new Promise(() => undefined));
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob })} />);

    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Journal entry validation" })).toBeInTheDocument();
    expect(screen.getByText("LOCAL_DETERMINISTIC")).toBeInTheDocument();
    expect(screen.getByText("0", { selector: "dd" })).toBeInTheDocument();

    const source = await chooseSource(user);
    const startButton = screen.getByRole("button", { name: "Start review" });
    expect(startButton).toBeDisabled();
    expect(startJob).not.toHaveBeenCalled();

    await user.click(screen.getByRole("checkbox", {
      name: "I confirm these are the intended source and reference inputs.",
    }));
    expect(startButton).toBeEnabled();
    expect(startJob).not.toHaveBeenCalled();

    await user.click(startButton);
    expect(await screen.findByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Profile workflows home" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Back to inventory" })).not.toBeInTheDocument();
    expect(startJob).toHaveBeenCalledTimes(1);
    expect(startJob.mock.calls[0][0]).toMatchObject({
      profileId: "journal-entries",
      entries: [expect.objectContaining({
        file: source,
        relativePath: "statement.pdf",
        purpose: "SOURCE",
        selected: true,
      })],
    });
    expect(startJob.mock.calls[0][0].idempotencyKey).toEqual(expect.any(String));
  });

  it("wires the folder chooser and retains its genuine nested relative path in the inventory", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>();
    render(<ProfileWorkspace adapter={makeAdapter({ startJob })} />);

    const folderInput = await screen.findByLabelText("Choose folder");
    expect(folderInput).toHaveAttribute("webkitdirectory", "");
    expect(folderInput).toHaveAttribute("directory", "");
    expect(folderInput).toHaveAttribute("tabindex", "-1");
    expect(screen.getByText("Choose folder", { selector: "button" })).toHaveProperty("tabIndex", 0);
    expect(screen.getByLabelText("Choose files")).toHaveAttribute("tabindex", "-1");
    expect(screen.getByText("Choose files", { selector: "button" })).toHaveProperty("tabIndex", 0);

    const inputClick = vi.spyOn(folderInput, "click").mockImplementation(() => undefined);
    await user.click(screen.getByText("Choose folder", { selector: "button" }));
    expect(inputClick).toHaveBeenCalledTimes(1);
    inputClick.mockRestore();

    const file = new File(["nested statement bytes"], "statement.pdf", { type: "application/pdf" });
    Object.defineProperty(file, "webkitRelativePath", {
      value: "client-pack/accounts/statement.pdf",
    });
    await user.upload(folderInput, file);

    expect(await screen.findByText("client-pack/accounts/statement.pdf")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Case / folder name" })).toHaveValue("client-pack");
    expect(startJob).not.toHaveBeenCalled();
  });

  it("keeps Start review disabled when only health is available", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>();
    render(<ProfileWorkspace adapter={makeAdapter({
      bootstrap: async () => ({
        ...bootstrapFixture,
        connection: {
          state: "HEALTH_ONLY",
          label: "Health only",
          detail: "The review bridge is unavailable.",
        },
      }),
      startJob,
    })} />);

    expect(await screen.findByText("Health only", { selector: "dd" })).toBeInTheDocument();
    await chooseSource(user);
    await user.click(screen.getByRole("checkbox", {
      name: "I confirm these are the intended source and reference inputs.",
    }));

    expect(screen.getByRole("button", { name: "Start review" })).toBeDisabled();
    await waitFor(() => expect(startJob).not.toHaveBeenCalled());
  });

  it("shows measured HTTP upload progress and locks manifest mutations in flight", async () => {
    const user = userEvent.setup();
    let acceptUpload: ((value: typeof startFixture) => void) | undefined;
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>((request) => {
      request.onUploadProgress?.({ loadedBytes: 50, totalBytes: 100, percentage: 50 });
      return new Promise((resolve) => { acceptUpload = resolve; });
    });
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>(() => new Promise(() => undefined));
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob })} />);

    await chooseSource(user);
    await user.click(screen.getByRole("checkbox", {
      name: "I confirm these are the intended source and reference inputs.",
    }));
    await user.click(screen.getByRole("button", { name: "Start review" }));

    expect(await screen.findByRole("button", { name: "Uploading 50%…" })).toBeDisabled();
    expect(screen.getByText("Measured HTTP upload: 50% · 50 B of 100 B")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Case / folder name" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Choose files" })).toBeDisabled();

    acceptUpload?.(startFixture);
    expect(await screen.findByRole("heading", { name: "Processing the selected files" })).toBeInTheDocument();
  });

  it("only offers backend-compatible purposes for each selected file format", async () => {
    const user = userEvent.setup();
    render(<ProfileWorkspace adapter={makeAdapter()} />);
    const source = new File(["pdf"], "statement.pdf", { type: "application/pdf" });
    const reference = new File(["xlsx"], "reference.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(await screen.findByLabelText("Choose files"), [source, reference]);

    const sourcePurpose = screen.getByLabelText("Purpose for statement.pdf");
    const referencePurpose = screen.getByLabelText("Purpose for reference.xlsx");
    expect(sourcePurpose).toHaveValue("SOURCE");
    expect(referencePurpose).toHaveValue("REFERENCE");
    expect(withinOptions(sourcePurpose)).toEqual(["Source"]);
    expect(withinOptions(referencePurpose)).toEqual(["Reference"]);
  });
});

function withinOptions(select: HTMLElement): string[] {
  return Array.from(select.querySelectorAll("option"), (option) => option.textContent ?? "");
}
