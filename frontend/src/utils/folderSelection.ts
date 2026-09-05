import type {
  BridgeCapabilities,
  CapabilityProfile,
  DiscoveredFile,
  FilePurpose,
  InventoryEntry,
} from "../workspaceTypes";

interface LegacyFileEntry {
  isFile: true;
  isDirectory: false;
  name: string;
  fullPath?: string;
  file(success: (file: File) => void, failure?: (error: DOMException) => void): void;
}

interface LegacyDirectoryReader {
  readEntries(
    success: (entries: LegacyEntry[]) => void,
    failure?: (error: DOMException) => void,
  ): void;
}

interface LegacyDirectoryEntry {
  isFile: false;
  isDirectory: true;
  name: string;
  fullPath?: string;
  createReader(): LegacyDirectoryReader;
}

export type LegacyEntry = LegacyFileEntry | LegacyDirectoryEntry;

export interface DropSnapshot {
  entries: LegacyEntry[];
  fallbackFiles: File[];
  usedDirectoryEntries: boolean;
}

const forbiddenDirectoryNames = new Set([
  ".git",
  ".svn",
  ".hg",
  ".env",
  ".credentials",
  "credentials",
  "node_modules",
  "bower_components",
  "jspm_packages",
  ".pnpm-store",
  "dependencies",
  "deps",
  "vendor",
  ".venv",
  "venv",
  "env",
  "site-packages",
  "__pycache__",
  ".tox",
  ".nox",
  ".mypy_cache",
  ".pytest_cache",
  "dist",
  "build",
  "coverage",
]);

const ambiguousDirectoryNames = new Set([
  "answer",
  "answers",
  "expected",
  "golden",
  "output",
  "outputs",
  "reference-answer",
  "reference-answers",
]);

export function snapshotDrop(dataTransfer: DataTransfer): DropSnapshot {
  const entries: LegacyEntry[] = [];
  let entryApiSeen = false;

  for (const item of Array.from(dataTransfer.items ?? [])) {
    if (item.kind !== "file") continue;
    const getEntry = (item as DataTransferItem & {
      webkitGetAsEntry?: () => LegacyEntry | null;
    }).webkitGetAsEntry;
    if (typeof getEntry === "function") {
      entryApiSeen = true;
      const entry = getEntry.call(item);
      if (entry) entries.push(entry);
    }
  }

  return {
    entries,
    fallbackFiles: Array.from(dataTransfer.files ?? []),
    usedDirectoryEntries: entryApiSeen && entries.length > 0,
  };
}

export async function resolveDrop(snapshot: DropSnapshot): Promise<DiscoveredFile[]> {
  if (snapshot.usedDirectoryEntries) {
    const nested = await Promise.all(snapshot.entries.map((entry) => traverseEntry(entry, [])));
    return nested.flat();
  }
  return filesToDiscovered(snapshot.fallbackFiles);
}

export function filesToDiscovered(files: Iterable<File>): DiscoveredFile[] {
  return Array.from(files, (file) => ({
    file,
    relativePath: normalizeBrowserPath(file.webkitRelativePath || file.name),
  }));
}

export async function traverseEntry(entry: LegacyEntry, parents: string[]): Promise<DiscoveredFile[]> {
  const currentPath = [...parents, entry.name];
  if (entry.isFile) {
    try {
      const file = await readFileEntry(entry);
      return [{ file, relativePath: normalizeBrowserPath(currentPath.join("/")) }];
    } catch (error) {
      return [{
        relativePath: normalizeBrowserPath(currentPath.join("/")),
        error: error instanceof Error ? error.message : "The browser could not read this file.",
      }];
    }
  }

  try {
    const children = await drainDirectory(entry.createReader());
    const nested = await Promise.all(children.map((child) => traverseEntry(child, currentPath)));
    return nested.flat();
  } catch (error) {
    return [{
      relativePath: normalizeBrowserPath(currentPath.join("/")),
      error: error instanceof Error ? error.message : "The browser could not read this folder.",
    }];
  }
}

export async function drainDirectory(reader: LegacyDirectoryReader): Promise<LegacyEntry[]> {
  const entries: LegacyEntry[] = [];
  while (true) {
    const batch = await readEntryBatch(reader);
    if (batch.length === 0) return entries;
    entries.push(...batch);
  }
}

export function buildInventory(
  discovered: DiscoveredFile[],
  profile: CapabilityProfile | undefined,
  limits: BridgeCapabilities["limits"] | undefined,
  existing: InventoryEntry[] = [],
): InventoryEntry[] {
  const seenPaths = new Set(existing.map((entry) => entry.relativePath));
  return discovered.map((item) => {
    const relativePath = normalizeBrowserPath(item.relativePath);
    const filename = relativePath.split("/").pop() || item.file?.name || "Unreadable item";
    const base: InventoryEntry = {
      clientFileId: makeClientId(),
      file: item.file,
      relativePath,
      filename,
      sizeBytes: item.file?.size ?? 0,
      contentType: item.file?.type || contentTypeFor(filename),
      status: "UNSUPPORTED",
      reason: "Backend workflow capabilities are unavailable.",
      selected: false,
    };

    const unsafePathReason = pathSafetyReason(relativePath, limits?.max_path_depth);
    if (unsafePathReason) return { ...base, status: "EXCLUDED", reason: unsafePathReason };
    if (seenPaths.has(relativePath)) {
      return { ...base, status: "EXCLUDED", reason: "This exact relative path is already in the inventory." };
    }
    seenPaths.add(relativePath);

    const parts = relativePath.split("/");
    const excludedReason = automaticExclusionReason(parts, filename);
    if (excludedReason) return { ...base, status: "EXCLUDED", reason: excludedReason };
    if (item.error || !item.file) {
      return { ...base, status: "UNREADABLE", reason: item.error || "The browser did not provide readable file bytes." };
    }
    if (item.file.size === 0) {
      return { ...base, status: "UNREADABLE", reason: "Empty files cannot be processed." };
    }
    if (limits && item.file.size > limits.max_file_bytes) {
      return {
        ...base,
        status: "UNSUPPORTED",
        reason: `File exceeds the ${formatBytes(limits.max_file_bytes)} per-file backend limit.`,
      };
    }
    if (!profile) return base;

    const extension = extensionOf(filename);
    const sourceFormats = new Set(profile.source.formats.map((format) => format.extension.toLowerCase()));
    const referenceFormats = new Set(profile.reference.formats.map((format) => format.extension.toLowerCase()));
    let purpose: FilePurpose | undefined;
    if (sourceFormats.has(extension)) purpose = "SOURCE";
    else if (referenceFormats.has(extension)) purpose = "REFERENCE";
    if (!purpose) {
      const accepted = [...sourceFormats, ...referenceFormats].join(", ");
      return {
        ...base,
        status: "UNSUPPORTED",
        reason: `Not supported by ${profile.label}. Accepted: ${accepted || "none advertised"}.`,
      };
    }

    const advertisedFormats = purpose === "SOURCE" ? profile.source.formats : profile.reference.formats;
    const advertisedFormat = advertisedFormats.find((format) => format.extension.toLowerCase() === extension);
    const suppliedContentType = item.file.type.split(";", 1)[0].trim().toLowerCase();
    const acceptedContentTypes = advertisedFormat?.content_types.map((contentType) => contentType.toLowerCase()) ?? [];
    if (suppliedContentType && !acceptedContentTypes.includes(suppliedContentType)) {
      return {
        ...base,
        purpose,
        status: "UNSUPPORTED",
        reason: `File MIME type ${suppliedContentType} does not match the backend-supported ${extension} type.`,
      };
    }

    const inAmbiguousFolder = parts
      .slice(0, -1)
      .some((part) => ambiguousDirectoryNames.has(part.toLowerCase()));
    if (inAmbiguousFolder) {
      return {
        ...base,
        purpose,
        status: "NEEDS_CONFIRMATION",
        reason: "This file is under an output or answer-like folder. Confirm it is a genuine input before selecting it.",
      };
    }

    return {
      ...base,
      purpose,
      status: "SUPPORTED",
      reason: purpose === "SOURCE" ? "Supported source document." : "Supported reference workbook.",
      selected: true,
    };
  });
}

export function selectionIssues(
  entries: InventoryEntry[],
  profile: CapabilityProfile | undefined,
  limits: BridgeCapabilities["limits"] | undefined,
): string[] {
  if (!profile || !limits) return ["Live backend capabilities are unavailable."];
  const selected = entries.filter((entry) => entry.selected);
  const sources = selected.filter((entry) => entry.purpose === "SOURCE");
  const references = selected.filter((entry) => entry.purpose === "REFERENCE");
  const issues: string[] = [];
  if (sources.length === 0) issues.push("Select at least one supported source PDF.");
  if (profile.reference.required && references.length === 0) issues.push("Select the required reference workbook.");
  if (references.length > profile.reference.max_files) {
    issues.push(`Select no more than ${profile.reference.max_files} reference workbook.`);
  }
  if (selected.length > limits.max_files) {
    issues.push(`${selected.length} files are selected; the backend limit is ${limits.max_files}. Nothing will be truncated.`);
  }
  const bytes = selected.reduce((total, entry) => total + entry.sizeBytes, 0);
  if (bytes > limits.max_batch_bytes) {
    issues.push(`${formatBytes(bytes)} is selected; the backend batch limit is ${formatBytes(limits.max_batch_bytes)}.`);
  }
  if (selected.some((entry) => !entry.file || entry.status === "UNREADABLE")) {
    issues.push("Remove unreadable selections before starting.");
  }
  const invalidPurposes = selected.filter((entry) => {
    if (!entry.purpose) return true;
    const extension = extensionOf(entry.filename);
    const formats = entry.purpose === "SOURCE" ? profile.source.formats : profile.reference.formats;
    return !formats.some((format) => format.extension.toLowerCase() === extension);
  });
  if (invalidPurposes.length > 0) {
    issues.push(`${invalidPurposes.length} selected ${invalidPurposes.length === 1 ? "file has" : "files have"} a purpose that does not match its backend-supported format.`);
  }
  return issues;
}

export function inferCaseName(entries: InventoryEntry[]): string {
  const live = entries.filter((entry) => entry.status !== "EXCLUDED");
  const top = new Set(live.map((entry) => entry.relativePath.split("/")[0]).filter(Boolean));
  if (top.size === 1) {
    const only = [...top][0];
    if (live.some((entry) => entry.relativePath.includes("/"))) return only;
  }
  return live.length === 1 ? live[0].filename.replace(/\.[^.]+$/, "") : "Untitled review pack";
}

export function inventoryGroups(entries: InventoryEntry[]): Array<{
  path: string;
  count: number;
  selected: number;
}> {
  const groups = new Map<string, { count: number; selected: number }>();
  for (const entry of entries) {
    const parts = entry.relativePath.split("/");
    const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : "Selected files";
    const current = groups.get(folder) ?? { count: 0, selected: 0 };
    current.count += 1;
    if (entry.selected) current.selected += 1;
    groups.set(folder, current);
  }
  return [...groups.entries()]
    .map(([path, counts]) => ({ path, ...counts }))
    .sort((left, right) => left.path.localeCompare(right.path));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}

function readFileEntry(entry: LegacyFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function readEntryBatch(reader: LegacyDirectoryReader): Promise<LegacyEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

function normalizeBrowserPath(path: string): string {
  return path;
}

function containsControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code <= 0x1f || code === 0x7f;
  });
}

function pathSafetyReason(path: string, maxDepth?: number): string | undefined {
  if (!path || path.startsWith("/") || path.includes("\\") || /^[A-Za-z]:\//.test(path)) {
    return "Absolute, empty, or non-POSIX paths are excluded.";
  }
  const parts = path.split("/");
  if (parts.some((part) => !part || part === "." || part === ".." || containsControlCharacter(part))) {
    return "Unsafe path components are excluded.";
  }
  if (maxDepth && parts.length - 1 > maxDepth) {
    return `Path depth exceeds the backend limit of ${maxDepth}.`;
  }
  return undefined;
}

function automaticExclusionReason(parts: string[], filename: string): string | undefined {
  const loweredParts = parts.map((part) => part.toLowerCase());
  const directory = loweredParts
    .slice(0, -1)
    .find((part) => forbiddenDirectoryNames.has(part) || part.startsWith(".env."));
  if (directory) return `Excluded dependency or system folder: ${directory}.`;

  const lower = filename.toLowerCase();
  if (lower === ".ds_store" || lower === "thumbs.db") return "Excluded operating-system metadata file.";
  if (lower === ".env" || lower.startsWith(".env.")) return "Excluded environment/credential file.";
  if (/credential|credentials|secret|private[_-]?key|service[_-]?account/.test(lower)
    || /^(id_rsa|id_ed25519)(\.|$)/.test(lower)
    || /\.(pem|key|p12|pfx)$/.test(lower)) {
    return "Excluded likely credential or private-key material.";
  }
  if (lower.startsWith("~$") || /\.(tmp|temp|swp|swo|bak|part|crdownload)$/.test(lower) || lower.endsWith("~")) {
    return "Excluded obvious temporary file.";
  }
  return undefined;
}

function extensionOf(filename: string): string {
  const index = filename.lastIndexOf(".");
  return index >= 0 ? filename.slice(index).toLowerCase() : "";
}

function contentTypeFor(filename: string): string {
  const extension = extensionOf(filename);
  if (extension === ".pdf") return "application/pdf";
  if (extension === ".xlsx") return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (extension === ".csv") return "text/csv";
  return "application/octet-stream";
}

let fallbackId = 0;
function makeClientId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  fallbackId += 1;
  return `client-file-${Date.now()}-${fallbackId}`;
}
