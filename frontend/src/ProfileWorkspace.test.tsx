import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  it("keeps selection locked until a compatible live capability profile is ready", async () => {
    const user = userEvent.setup();
    let resolveBootstrap!: (value: typeof bootstrapFixture) => void;
    const bootstrap = vi.fn<WorkspaceAdapter["bootstrap"]>(() => new Promise((resolve) => {
      resolveBootstrap = resolve;
    }));
    render(<ProfileWorkspace adapter={makeAdapter({ bootstrap })} />);

    const chooseFiles = screen.getByRole("button", { name: "Choose files" });
    expect(chooseFiles).toBeDisabled();
    const dropzone = screen.getByText("Drop one folder or multiple files").closest(".folder-dropzone")!;
    const earlyFile = new File(["early bytes"], "early.pdf", { type: "application/pdf" });
    fireEvent.drop(dropzone, { dataTransfer: { items: [], files: [earlyFile] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Wait for the live backend");
    expect(screen.queryByText("early.pdf")).not.toBeInTheDocument();

    await act(async () => resolveBootstrap(bootstrapFixture));
    await waitFor(() => expect(chooseFiles).toBeEnabled());
    await user.upload(screen.getByLabelText("Choose files"), earlyFile);
    expect(await screen.findByText("early.pdf")).toBeInTheDocument();
  });

  it("enables one PDF immediately and starts once only when the reviewer chooses Start review", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>().mockResolvedValue(startFixture);
    const getJob = vi.fn<WorkspaceAdapter["getJob"]>(() => new Promise(() => undefined));
    render(<ProfileWorkspace adapter={makeAdapter({ startJob, getJob })} />);

    expect(await screen.findByRole("heading", { name: "Drop a folder to start a review" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Bank statement validation" })).toBeInTheDocument();
    expect(screen.getByText("LOCAL_DETERMINISTIC")).toBeInTheDocument();
    expect(screen.getByText("0", { selector: "dd" })).toBeInTheDocument();

    const source = await chooseSource(user);
    const startButton = screen.getByRole("button", { name: "Start review" });
    expect(startButton).toBeEnabled();
    expect(startJob).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox", { name: /I confirm/ })).not.toBeInTheDocument();

    fireEvent.click(startButton);
    fireEvent.click(startButton);
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
    expect(folderInput).toHaveAttribute("hidden");
    expect(screen.getAllByRole("button", { name: "Choose folder" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Choose folder" })).toHaveProperty("tabIndex", 0);
    expect(screen.getByLabelText("Choose files")).toHaveAttribute("hidden");
    expect(screen.getAllByRole("button", { name: "Choose files" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Choose files" })).toHaveProperty("tabIndex", 0);

    const inputClick = vi.spyOn(folderInput, "click").mockImplementation(() => undefined);
    await user.click(screen.getByRole("button", { name: "Choose folder" }));
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

  it("surfaces a folder-picker fallback when the browser entry API throws", async () => {
    render(<ProfileWorkspace adapter={makeAdapter()} />);
    const prompt = await screen.findByText("Drop one folder or multiple files");
    const dropzone = prompt.closest(".folder-dropzone")!;

    fireEvent.drop(dropzone, {
      dataTransfer: {
        items: [{
          kind: "file",
          webkitGetAsEntry: () => { throw new DOMException("Provider denied access"); },
        }],
        files: [],
      },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing was added. Use Choose folder to preserve the complete nested inventory.",
    );
    expect(screen.getByRole("button", { name: "Choose folder" })).toBeEnabled();
  });

  it("keeps selection and Start review unavailable when only health is available", async () => {
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
    expect(screen.getByRole("button", { name: "Choose folder" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Choose files" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Start review" })).not.toBeInTheDocument();
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

  it("prefers bank statement validation and labels both deterministic choices accurately", async () => {
    const user = userEvent.setup();
    const pipeline = { ...bootstrapFixture.profiles[0], id: "pipeline-validation", label: "Model and pipeline validation" };
    const capabilities = bootstrapFixture.capabilities!;
    render(<ProfileWorkspace adapter={makeAdapter({
      bootstrap: async () => ({
        ...bootstrapFixture,
        profiles: [pipeline, { ...bootstrapFixture.profiles[0], label: "Bank statements to journal entries" }],
        capabilities: {
          ...capabilities,
          profiles: [{ ...capabilities.profiles[0], profile_id: "pipeline-validation" }, ...capabilities.profiles],
        },
      }),
    })} />);

    expect(await screen.findByRole("option", { name: "Bank statement validation" })).toBeInTheDocument();
    const workflow = screen.getByRole("combobox", { name: "Supported workflow" });
    expect(workflow).toHaveValue("journal-entries");
    expect(screen.getByText(/This workflow makes no model calls and does not classify payments/)).toBeInTheDocument();
    await user.selectOptions(workflow, "pipeline-validation");
    expect(screen.getByRole("option", { name: "Statement validation package" })).toBeInTheDocument();
    expect(screen.getByText(/Model evaluation, payment resolution and classification are not run/)).toBeInTheDocument();
    await chooseSource(user);
    expect(screen.getByRole("button", { name: "Start review" })).toBeEnabled();
  });

  it("still requires per-file selection for an ambiguous output-folder PDF", async () => {
    const user = userEvent.setup();
    const startJob = vi.fn<WorkspaceAdapter["startJob"]>();
    render(<ProfileWorkspace adapter={makeAdapter({ startJob })} />);
    const file = new File(["source bytes"], "statement.pdf", { type: "application/pdf" });
    Object.defineProperty(file, "webkitRelativePath", { value: "pack/outputs/statement.pdf" });
    await user.upload(await screen.findByLabelText("Choose folder"), file);

    const start = screen.getByRole("button", { name: "Start review" });
    expect(start).toBeDisabled();
    const include = screen.getByRole("checkbox", { name: "Include pack/outputs/statement.pdf" });
    expect(include).not.toBeChecked();
    await user.click(include);
    expect(start).toBeEnabled();
    expect(startJob).not.toHaveBeenCalled();
  });

  it("retries an initially unavailable backend and enables the file picker once connected", async () => {
    const user = userEvent.setup();
    const bootstrap = vi.fn<WorkspaceAdapter["bootstrap"]>()
      .mockRejectedValueOnce(new Error("backend starting"))
      .mockResolvedValueOnce(bootstrapFixture);
    render(<ProfileWorkspace adapter={makeAdapter({ bootstrap })} />);

    await user.click(await screen.findByRole("button", { name: "Retry connection" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Choose files" })).toBeEnabled());
    expect(bootstrap).toHaveBeenCalledTimes(2);
    await chooseSource(user);
    expect(screen.getByRole("button", { name: "Start review" })).toBeEnabled();
  });
});

function withinOptions(select: HTMLElement): string[] {
  return Array.from(select.querySelectorAll("option"), (option) => option.textContent ?? "");
}
