import { describe, expect, it, vi } from "vitest";
import {
  buildInventory,
  drainDirectory,
  filesToDiscovered,
  resolveDrop,
  selectionIssues,
  snapshotDrop,
  traverseEntry,
  type LegacyEntry,
} from "./folderSelection";
import { capabilitiesFixture } from "../test/workspaceFixtures";
import type { DiscoveredFile, InventoryEntry } from "../workspaceTypes";

const profile = capabilitiesFixture.profiles[0];
const limits = capabilitiesFixture.limits;

function pdf(name: string, contents = "pdf bytes"): File {
  return new File([contents], name, { type: "application/pdf" });
}

function xlsx(name: string, contents = "xlsx bytes"): File {
  return new File([contents], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function fileEntry(name: string, file = pdf(name)): LegacyEntry {
  return {
    isFile: true,
    isDirectory: false,
    name,
    file(success) { success(file); },
  };
}

function directoryEntry(name: string, batches: LegacyEntry[][]): LegacyEntry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader() {
      let index = 0;
      return {
        readEntries(success) {
          success(batches[index++] ?? []);
        },
      };
    },
  };
}

describe("folder traversal", () => {
  it("rejects a partial directory-entry snapshot instead of silently omitting fallback-only files", async () => {
    const exposedEntry = fileEntry("visible.pdf");
    const visibleFile = pdf("visible.pdf");
    const hiddenFile = pdf("hidden.pdf");
    const dataTransfer = {
      items: [
        { kind: "file", webkitGetAsEntry: () => exposedEntry },
        { kind: "file", webkitGetAsEntry: () => null },
      ],
      files: [visibleFile, hiddenFile],
    } as unknown as DataTransfer;

    const snapshot = snapshotDrop(dataTransfer);

    expect(snapshot).toMatchObject({
      usedDirectoryEntries: true,
      hasPartialDirectoryEntries: true,
      fallbackFiles: [visibleFile, hiddenFile],
    });
    await expect(resolveDrop(snapshot)).rejects.toThrow(
      "This browser exposed only part of the dropped folder.",
    );
  });

  it("drains every directory-reader batch instead of stopping at the first 100 entries", async () => {
    const files = Array.from({ length: 137 }, (_, index) => fileEntry(`statement-${index}.pdf`));
    const readEntries = vi.fn<(success: (entries: LegacyEntry[]) => void) => void>();
    const batches = [files.slice(0, 100), files.slice(100), []];
    readEntries.mockImplementation((success) => success(batches.shift() ?? []));

    const drained = await drainDirectory({ readEntries });

    expect(drained).toHaveLength(137);
    expect(readEntries).toHaveBeenCalledTimes(3);
  });

  it("retains the complete nested relative path for more than 100 dropped files", async () => {
    const files = Array.from({ length: 125 }, (_, index) => fileEntry(`statement-${index}.pdf`));
    const root = directoryEntry("client-pack", [files.slice(0, 100), files.slice(100), []]);

    const discovered = await traverseEntry(root, []);

    expect(discovered).toHaveLength(125);
    expect(discovered[0]).toMatchObject({ relativePath: "client-pack/statement-0.pdf" });
    expect(discovered[124]).toMatchObject({ relativePath: "client-pack/statement-124.pdf" });
    expect(discovered.every((item) => item.file instanceof File)).toBe(true);
  });

  it("preserves webkitRelativePath from the folder picker", () => {
    const file = pdf("operating.pdf");
    Object.defineProperty(file, "webkitRelativePath", { value: "fund/accounts/operating.pdf" });

    expect(filesToDiscovered([file])).toEqual([{ file, relativePath: "fund/accounts/operating.pdf" }]);
  });

  it("keeps same-named leaf files in different folders and excludes only an exact relative-path duplicate", () => {
    const first = buildInventory([
      { file: pdf("statement.pdf"), relativePath: "pack/account-a/statement.pdf" },
      { file: pdf("statement.pdf"), relativePath: "pack/account-b/statement.pdf" },
      { file: pdf("statement.pdf"), relativePath: "pack/account-a/statement.pdf" },
    ], profile, limits);

    expect(first[0]).toMatchObject({ status: "SUPPORTED", selected: true, purpose: "SOURCE" });
    expect(first[1]).toMatchObject({ status: "SUPPORTED", selected: true, purpose: "SOURCE" });
    expect(first[2]).toMatchObject({
      status: "EXCLUDED",
      selected: false,
      reason: "This exact relative path is already in the inventory.",
    });

    const later = buildInventory([
      { file: pdf("statement.pdf"), relativePath: "pack/account-b/statement.pdf" },
    ], profile, limits, first);
    expect(later[0].status).toBe("EXCLUDED");
  });

  it("uses NFC and common case-insensitive path identity when detecting duplicates", () => {
    const entries = buildInventory([
      { file: pdf("Évidence.pdf"), relativePath: "Pack/Évidence.pdf" },
      { file: pdf("ÉVIDENCE.PDF"), relativePath: "pack/ÉVIDENCE.PDF" },
    ], profile, limits);

    expect(entries[0]).toMatchObject({ status: "SUPPORTED", selected: true });
    expect(entries[1]).toMatchObject({
      status: "EXCLUDED",
      selected: false,
      reason: "This exact relative path is already in the inventory.",
    });
  });
});

describe("inventory policy", () => {
  it.each([
    ["pack/.git/objects/one.pdf", "Excluded dependency or system folder"],
    ["pack/.env/statement.pdf", "Excluded dependency or system folder"],
    ["pack/.env.production/statement.pdf", "Excluded dependency or system folder"],
    ["pack/.credentials/statement.pdf", "Excluded dependency or system folder"],
    ["pack/credentials/statement.pdf", "Excluded dependency or system folder"],
    ["pack/node_modules/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/jspm_packages/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/.pnpm-store/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/dependencies/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/deps/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/env/statement.pdf", "Excluded dependency or system folder"],
    ["pack/site-packages/vendor.pdf", "Excluded dependency or system folder"],
    ["pack/.tox/statement.pdf", "Excluded dependency or system folder"],
    ["pack/.nox/statement.pdf", "Excluded dependency or system folder"],
    ["pack/.mypy_cache/statement.pdf", "Excluded dependency or system folder"],
    ["pack/.env.production", "Excluded environment/credential file"],
    ["pack/service-account.xlsx", "Excluded likely credential"],
    ["pack/id_rsa", "Excluded likely credential"],
    ["pack/client-private-key.pem", "Excluded likely credential"],
    ["pack/~$reference.xlsx", "Excluded obvious temporary file"],
    ["pack/notes.tmp", "Excluded obvious temporary file"],
    ["pack/notes.bak", "Excluded obvious temporary file"],
    ["pack/download.part", "Excluded obvious temporary file"],
    ["pack/download.crdownload", "Excluded obvious temporary file"],
    ["pack/.DS_Store", "Excluded operating-system metadata"],
  ])("automatically excludes %s with an explicit reason", (relativePath, reason) => {
    const file = relativePath.endsWith(".xlsx") ? xlsx(relativePath.split("/").at(-1)!) : pdf(relativePath.split("/").at(-1)!);
    const [entry] = buildInventory([{ file, relativePath }], profile, limits);

    expect(entry).toMatchObject({ status: "EXCLUDED", selected: false });
    expect(entry.reason).toContain(reason);
  });

  it("requires explicit per-file confirmation for answer/output-like folders", () => {
    const [entry] = buildInventory([
      { file: pdf("statement.pdf"), relativePath: "pack/expected/statement.pdf" },
    ], profile, limits);

    expect(entry).toMatchObject({
      status: "NEEDS_CONFIRMATION",
      selected: false,
      purpose: "SOURCE",
    });
    expect(entry.reason).toContain("genuine input");
  });

  it.each([0, 9, 10, 31, 127])(
    "excludes paths containing backend-forbidden control character %i before upload",
    (characterCode) => {
      const relativePath = `pack/unsafe${String.fromCharCode(characterCode)}name.pdf`;
      const [entry] = buildInventory([{ file: pdf("statement.pdf"), relativePath }], profile, limits);

      expect(entry).toMatchObject({
        status: "EXCLUDED",
        selected: false,
        reason: "Unsafe path components are excluded.",
      });
    },
  );

  it("excludes backslash-delimited or backslash-containing browser paths instead of rewriting their identity", () => {
    const [entry] = buildInventory([
      { file: pdf("statement.pdf"), relativePath: "pack\\account\\statement.pdf" },
    ], profile, limits);

    expect(entry).toMatchObject({
      relativePath: "pack\\account\\statement.pdf",
      status: "EXCLUDED",
      selected: false,
      reason: "Absolute, empty, or non-POSIX paths are excluded.",
    });
  });

  it.each([
    ["C:statement.pdf", "Absolute, empty, or non-POSIX paths are excluded."],
    [`pack/${"a".repeat(252)}.pdf`, "Filename exceeds the backend limit of 255 characters."],
    [`${"folder/".repeat(150)}statement.pdf`, "Relative path exceeds the backend limit of 1024 characters."],
    [" pack/statement.pdf", "Paths and filenames with surrounding whitespace are excluded."],
    ["pack/statement.pdf ", "Paths and filenames with surrounding whitespace are excluded."],
  ])("rejects browser path %s before the backend would reject its manifest", (relativePath, reason) => {
    const filename = relativePath.split("/").at(-1) || "statement.pdf";
    const [entry] = buildInventory([
      { file: pdf(filename), relativePath },
    ], profile, limits);

    expect(entry).toMatchObject({ status: "EXCLUDED", selected: false, reason });
  });

  it("reports unreadable, empty, unsupported, oversized and over-depth entries without truncation", () => {
    const oversized = pdf("huge.pdf");
    Object.defineProperty(oversized, "size", { value: limits.max_file_bytes + 1 });
    const empty = new File([], "empty.pdf", { type: "application/pdf" });
    const discovered: DiscoveredFile[] = [
      { relativePath: "pack/could-not-read.pdf", error: "Permission denied" },
      { file: empty, relativePath: "pack/empty.pdf" },
      { file: new File(["doc"], "notes.docx"), relativePath: "pack/notes.docx" },
      { file: oversized, relativePath: "pack/huge.pdf" },
      { file: pdf("deep.pdf"), relativePath: "a/b/c/d/e/deep.pdf" },
    ];

    const entries = buildInventory(discovered, profile, { ...limits, max_path_depth: 4 });

    expect(entries).toHaveLength(5);
    expect(entries.map((entry) => entry.status)).toEqual([
      "UNREADABLE",
      "UNREADABLE",
      "UNSUPPORTED",
      "UNSUPPORTED",
      "EXCLUDED",
    ]);
    expect(entries[0].reason).toBe("Permission denied");
    expect(entries[1].reason).toContain("Empty files");
    expect(entries[2].reason).toContain("Not supported");
    expect(entries[3].reason).toContain("per-file backend limit");
    expect(entries[4].reason).toContain("Path depth exceeds");
  });

  it("accepts exactly the advertised number of nested directories", () => {
    const [entry] = buildInventory([
      { file: pdf("boundary.pdf"), relativePath: "a/b/c/d/boundary.pdf" },
    ], profile, { ...limits, max_path_depth: 4 });

    expect(entry).toMatchObject({ status: "SUPPORTED", selected: true });
  });

  it("rejects a conflicting browser MIME but accepts a missing MIME for safe adapter normalization", () => {
    const wrongType = new File(["pdf"], "wrong.pdf", { type: "text/plain" });
    const missingType = new File(["pdf"], "missing.pdf");
    const entries = buildInventory([
      { file: wrongType, relativePath: "pack/wrong.pdf" },
      { file: missingType, relativePath: "pack/missing.pdf" },
    ], profile, limits);

    expect(entries[0]).toMatchObject({
      status: "UNSUPPORTED",
      selected: false,
      reason: "File MIME type text/plain does not match the backend-supported .pdf type.",
    });
    expect(entries[1]).toMatchObject({
      status: "SUPPORTED",
      selected: true,
      contentType: "application/pdf",
    });
  });

  it("enforces required inputs, reference count, selected-file count, batch bytes and readability", () => {
    const makeEntry = (overrides: Partial<InventoryEntry>): InventoryEntry => ({
      clientFileId: crypto.randomUUID(),
      file: pdf("source.pdf"),
      relativePath: "pack/source.pdf",
      filename: "source.pdf",
      sizeBytes: 8,
      contentType: "application/pdf",
      status: "SUPPORTED",
      reason: "Supported source document.",
      selected: true,
      purpose: "SOURCE",
      ...overrides,
    });
    const strictProfile = {
      ...profile,
      reference: { ...profile.reference, required: true, max_files: 1 },
    };
    expect(selectionIssues([], strictProfile, limits)).toEqual([
      "Select at least one supported source PDF.",
      "Select the required reference workbook.",
    ]);

    const entries = [
      makeEntry({ clientFileId: "source", sizeBytes: 70 }),
      makeEntry({ clientFileId: "ref-1", purpose: "REFERENCE", filename: "one.xlsx", relativePath: "pack/one.xlsx", file: xlsx("one.xlsx"), sizeBytes: 40 }),
      makeEntry({ clientFileId: "ref-2", purpose: "REFERENCE", filename: "two.xlsx", relativePath: "pack/two.xlsx", file: xlsx("two.xlsx"), sizeBytes: 1 }),
      makeEntry({ clientFileId: "bad", file: undefined, status: "UNREADABLE", sizeBytes: 0 }),
    ];
    const issues = selectionIssues(entries, strictProfile, { ...limits, max_files: 3, max_batch_bytes: 100 });

    expect(issues).toEqual(expect.arrayContaining([
      "Select no more than 1 reference workbook.",
      "4 files are selected; the backend limit is 3. Nothing will be truncated.",
      "111 B is selected; the backend batch limit is 100 B.",
      "Remove unreadable selections before starting.",
    ]));
  });

  it("rejects selected purposes that do not match the profile format even if state is tampered with", () => {
    const sourceFile = pdf("valid.pdf");
    const wrongReferenceFile = pdf("wrong-reference.pdf");
    const wrongSourceFile = xlsx("wrong-source.xlsx");
    const entries: InventoryEntry[] = [{
      clientFileId: "valid-source",
      file: sourceFile,
      relativePath: "pack/valid.pdf",
      filename: "valid.pdf",
      sizeBytes: sourceFile.size,
      contentType: sourceFile.type,
      status: "SUPPORTED",
      reason: "Supported source document.",
      selected: true,
      purpose: "SOURCE",
    }, {
      clientFileId: "wrong-reference",
      file: wrongReferenceFile,
      relativePath: "pack/wrong-reference.pdf",
      filename: "wrong-reference.pdf",
      sizeBytes: wrongReferenceFile.size,
      contentType: wrongReferenceFile.type,
      status: "SUPPORTED",
      reason: "Tampered purpose.",
      selected: true,
      purpose: "REFERENCE",
    }, {
      clientFileId: "wrong-source",
      file: wrongSourceFile,
      relativePath: "pack/wrong-source.xlsx",
      filename: "wrong-source.xlsx",
      sizeBytes: wrongSourceFile.size,
      contentType: wrongSourceFile.type,
      status: "SUPPORTED",
      reason: "Tampered purpose.",
      selected: true,
      purpose: "SOURCE",
    }];

    expect(selectionIssues(entries, profile, limits)).toContain(
      "2 selected files have a purpose that does not match its backend-supported format.",
    );
  });
});
