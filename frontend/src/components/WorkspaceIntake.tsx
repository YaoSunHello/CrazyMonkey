import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import type {
  BackendConnection,
  BackendProfileSummary,
  BridgeCapabilities,
  CapabilityProfile,
  DiscoveredFile,
  FilePurpose,
  InventoryEntry,
  ReplaySummary,
  UploadProgress,
} from "../workspaceTypes";
import {
  filesToDiscovered,
  formatBytes,
  inventoryGroups,
  resolveDrop,
  snapshotDrop,
} from "../utils/folderSelection";

const pageSize = 50;

interface WorkspaceIntakeProps {
  connection: BackendConnection;
  profiles: BackendProfileSummary[];
  capabilities?: BridgeCapabilities;
  capabilityProfile?: CapabilityProfile;
  profileId: string;
  caseName: string;
  entries: InventoryEntry[];
  issues: string[];
  replays: ReplaySummary[];
  busy: boolean;
  uploadProgress?: UploadProgress;
  confirmed: boolean;
  onProfileChange(profileId: string): void;
  onCaseNameChange(value: string): void;
  onDiscovered(files: DiscoveredFile[]): void;
  onToggle(clientFileId: string, selected: boolean): void;
  onPurpose(clientFileId: string, purpose: FilePurpose): void;
  onRemove(clientFileId: string): void;
  onConfirm(value: boolean): void;
  onStart(): void;
  onOpenReplay(replayId: string): void;
  onNotice(message: string, tone?: "info" | "error"): void;
}

export function WorkspaceIntake({
  connection,
  profiles,
  capabilities,
  capabilityProfile,
  profileId,
  caseName,
  entries,
  issues,
  replays,
  busy,
  uploadProgress,
  confirmed,
  onProfileChange,
  onCaseNameChange,
  onDiscovered,
  onToggle,
  onPurpose,
  onRemove,
  onConfirm,
  onStart,
  onOpenReplay,
  onNotice,
}: WorkspaceIntakeProps) {
  const folderId = useId();
  const filesId = useId();
  const folderRef = useRef<HTMLInputElement>(null);
  const filesRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"ALL" | InventoryEntry["status"]>("ALL");
  const [page, setPage] = useState(0);
  const [replayId, setReplayId] = useState(replays[0]?.replay_id ?? "");

  useEffect(() => {
    folderRef.current?.setAttribute("webkitdirectory", "");
    folderRef.current?.setAttribute("directory", "");
  }, []);

  const selected = entries.filter((entry) => entry.selected);
  const selectedBytes = selected.reduce((total, entry) => total + entry.sizeBytes, 0);
  const excluded = entries.filter((entry) => entry.status === "EXCLUDED").length;
  const unsupported = entries.filter((entry) => entry.status === "UNSUPPORTED").length;
  const unreadable = entries.filter((entry) => entry.status === "UNREADABLE").length;
  const needsConfirmation = entries.filter((entry) => entry.status === "NEEDS_CONFIRMATION").length;
  const groups = inventoryGroups(entries);
  const filtered = useMemo(
    () => statusFilter === "ALL" ? entries : entries.filter((entry) => entry.status === statusFilter),
    [entries, statusFilter],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pages - 1);
  const visible = filtered.slice(safePage * pageSize, (safePage + 1) * pageSize);
  const effectiveReplayId = replays.some((item) => item.replay_id === replayId)
    ? replayId
    : replays[0]?.replay_id ?? "";
  const canStart = connection.state === "CONNECTED" && confirmed && issues.length === 0 && !busy && !scanning;
  const supportedFormats = capabilityProfile
    ? [...capabilityProfile.source.formats, ...capabilityProfile.reference.formats]
      .map((format) => format.extension.toUpperCase())
      .join(", ")
    : "Waiting for backend capabilities";

  async function handleFiles(fileList: FileList | null, input: HTMLInputElement | null) {
    if (busy || scanning) return;
    if (!fileList?.length) return;
    onDiscovered(filesToDiscovered(fileList));
    if (input) input.value = "";
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (busy || scanning) return;
    setScanning(true);
    try {
      const snapshot = snapshotDrop(event.dataTransfer);
      const discovered = await resolveDrop(snapshot);
      if (discovered.length === 0) {
        onNotice(
          snapshot.usedDirectoryEntries
            ? "The folder traversal completed but yielded no readable files. Try Choose folder if the browser blocked drag-and-drop access."
            : "This browser did not expose folder entries. Use Choose folder to preserve nested paths.",
          "error",
        );
        return;
      }
      onDiscovered(discovered);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "The dropped folder could not be read.";
      onNotice(`${detail} Nothing was added. Use Choose folder to preserve the complete nested inventory.`, "error");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="intake-page">
      <section className="intake-intro" aria-labelledby="intake-title">
        <p className="eyebrow">New financial review</p>
        <h1 id="intake-title" tabIndex={-1}>Drop a folder to start a review</h1>
        <p className="intake-lede">
          Inspect the complete pack first. Processing begins only after you select a supported workflow,
          confirm the source set and choose <strong>Start review</strong>.
        </p>

        <dl className="connection-card">
          <div>
            <dt>Backend</dt>
            <dd><span className={`connection-dot connection-${connection.state.toLowerCase()}`} />{connection.label}</dd>
          </div>
          <div>
            <dt>Execution</dt>
            <dd>{capabilities?.execution.label ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>Model calls</dt>
            <dd>{capabilities ? String(capabilities.execution.model_calls) : "—"}</dd>
          </div>
        </dl>
        <p className="connection-detail">{connection.detail}</p>

        <div className="replay-control">
          <div>
            <strong>Need a safe walkthrough?</strong>
            <p>Open a committed, genuine result. It makes zero model calls and is labelled as recorded playback.</p>
          </div>
          <div className="replay-actions">
            <label className="visually-hidden" htmlFor="recorded-run">Recorded run</label>
            <select
              id="recorded-run"
              value={effectiveReplayId}
              onChange={(event) => setReplayId(event.target.value)}
              disabled={replays.length === 0 || busy || scanning}
            >
              {replays.length === 0 && <option value="">No recorded runs available</option>}
              {replays.map((replay) => (
                <option key={replay.replay_id} value={replay.replay_id}>
                  {replay.profile_id} · {replay.original_run_ids.length} documents
                </option>
              ))}
            </select>
            <button
              className="button button-secondary"
              type="button"
              disabled={!effectiveReplayId || busy || scanning}
              onClick={() => onOpenReplay(effectiveReplayId)}
            >
              Open recorded run
            </button>
          </div>
        </div>
      </section>

      <section className="intake-workbench" aria-labelledby="pack-heading">
        <div className="workbench-heading">
          <div>
            <p className="step-label">1 · Select and inspect</p>
            <h2 id="pack-heading">Review pack inventory</h2>
          </div>
          <span className="mode-label mode-live">LIVE</span>
        </div>

        <div className="intake-fields">
          <label>
            <span>Case / folder name</span>
            <input
              value={caseName}
              maxLength={120}
              disabled={busy || scanning}
              onChange={(event) => onCaseNameChange(event.target.value)}
              placeholder="e.g. March 2026 bank statements"
            />
          </label>
          <label>
            <span>Supported workflow</span>
            <select value={profileId} onChange={(event) => onProfileChange(event.target.value)} disabled={!profiles.length || busy || scanning}>
              {!profiles.length && <option value="">No live profiles available</option>}
              {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}
            </select>
          </label>
        </div>
        {profiles.find((profile) => profile.id === profileId)?.description && (
          <p className="profile-description">{profiles.find((profile) => profile.id === profileId)?.description}</p>
        )}

        <div
          className={`folder-dropzone ${dragActive ? "is-dragging" : ""} ${busy || scanning ? "is-locked" : ""}`}
          aria-disabled={busy || scanning}
          onDragEnter={(event) => { event.preventDefault(); if (!busy && !scanning) setDragActive(true); }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = busy || scanning ? "none" : "copy"; }}
          onDragLeave={(event) => { if (event.currentTarget === event.target) setDragActive(false); }}
          onDrop={(event) => void handleDrop(event)}
        >
          <div className="dropzone-icon" aria-hidden="true">↓</div>
          <div>
            <strong>{scanning ? "Reading the complete folder tree…" : "Drop one folder or multiple files"}</strong>
            <p>{supportedFormats} · nested paths retained · nothing starts automatically</p>
          </div>
          <div className="picker-actions">
            <input
              ref={folderRef}
              id={folderId}
              type="file"
              aria-label="Choose folder"
              hidden
              tabIndex={-1}
              multiple
              disabled={busy || scanning}
              onChange={(event) => void handleFiles(event.target.files, folderRef.current)}
            />
            <button
              className="button button-primary"
              type="button"
              aria-controls={folderId}
              disabled={busy || scanning}
              onClick={() => folderRef.current?.click()}
            >
              Choose folder
            </button>
            <input
              ref={filesRef}
              id={filesId}
              type="file"
              aria-label="Choose files"
              hidden
              tabIndex={-1}
              multiple
              disabled={busy || scanning}
              accept={supportedFormats.includes("Waiting") ? undefined : supportedFormats.toLowerCase().replaceAll(" ", "")}
              onChange={(event) => void handleFiles(event.target.files, filesRef.current)}
            />
            <button
              className="button button-secondary"
              type="button"
              aria-controls={filesId}
              disabled={busy || scanning}
              onClick={() => filesRef.current?.click()}
            >
              Choose files
            </button>
          </div>
        </div>

        {capabilities && (
          <p className="limits-line">
            Backend limits: {capabilities.limits.max_files} selected files · {formatBytes(capabilities.limits.max_file_bytes)} per file · {formatBytes(capabilities.limits.max_batch_bytes)} total · {capabilities.limits.max_path_depth} nested directories
          </p>
        )}

        {entries.length > 0 && (
          <div className="inventory-area">
            <div className="inventory-summary" aria-label="Inventory summary">
              <span><strong>{entries.length}</strong> discovered</span>
              <span><strong>{selected.length}</strong> selected</span>
              <span><strong>{formatBytes(selectedBytes)}</strong> selected size</span>
              <span><strong>{excluded}</strong> excluded</span>
              <span><strong>{unsupported}</strong> unsupported</span>
              <span><strong>{unreadable}</strong> unreadable</span>
              <span><strong>{needsConfirmation}</strong> confirm</span>
            </div>

            <div className="inventory-grid">
              <aside className="folder-tree" aria-label="Folder tree">
                <h3>Folders</h3>
                <ul>
                  {groups.map((group) => (
                    <li key={group.path}>
                      <span aria-hidden="true">▸</span>
                      <span title={group.path}>{group.path}</span>
                      <small>{group.selected}/{group.count}</small>
                    </li>
                  ))}
                </ul>
              </aside>

              <div className="inventory-table-wrap">
                <div className="inventory-toolbar">
                  <div className="filter-tabs" role="group" aria-label="Filter inventory">
                    {(["ALL", "SUPPORTED", "NEEDS_CONFIRMATION", "EXCLUDED", "UNSUPPORTED", "UNREADABLE"] as const).map((status) => (
                      <button
                        key={status}
                        type="button"
                        className={statusFilter === status ? "is-active" : ""}
                        onClick={() => { setStatusFilter(status); setPage(0); }}
                      >
                        {status === "ALL" ? "All" : status.replace("_", " ").toLowerCase()}
                      </button>
                    ))}
                  </div>
                  <span>Showing {filtered.length === 0 ? 0 : safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, filtered.length)} of {filtered.length}</span>
                </div>

                <table className="inventory-table">
                  <thead>
                    <tr>
                      <th scope="col">Use</th>
                      <th scope="col">Relative path</th>
                      <th scope="col">Purpose</th>
                      <th scope="col" className="numeric">Size</th>
                      <th scope="col">Status</th>
                      <th scope="col"><span className="visually-hidden">Remove</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((entry) => {
                      const selectable = entry.status === "SUPPORTED" || entry.status === "NEEDS_CONFIRMATION";
                      const purposes = purposesFor(entry, capabilityProfile);
                      return (
                        <tr key={entry.clientFileId}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Include ${entry.relativePath}`}
                              checked={entry.selected}
                              disabled={!selectable || busy || scanning}
                              onChange={(event) => onToggle(entry.clientFileId, event.target.checked)}
                            />
                          </td>
                          <td className="path-cell" title={entry.relativePath}>{entry.relativePath}</td>
                          <td>
                            {entry.purpose ? (
                              <select
                                aria-label={`Purpose for ${entry.relativePath}`}
                                value={entry.purpose}
                                disabled={!selectable || busy || scanning}
                                onChange={(event) => onPurpose(entry.clientFileId, event.target.value as FilePurpose)}
                              >
                                {purposes.includes("SOURCE") && <option value="SOURCE">Source</option>}
                                {purposes.includes("REFERENCE") && <option value="REFERENCE">Reference</option>}
                              </select>
                            ) : "—"}
                          </td>
                          <td className="numeric">{formatBytes(entry.sizeBytes)}</td>
                          <td>
                            <span className={`inventory-status inventory-${entry.status.toLowerCase()}`}>{entry.status.replace("_", " ")}</span>
                            <small className="status-reason">{entry.reason}</small>
                          </td>
                          <td>
                            <button className="icon-button" type="button" disabled={busy || scanning} aria-label={`Remove ${entry.relativePath}`} onClick={() => onRemove(entry.clientFileId)}>×</button>
                          </td>
                        </tr>
                      );
                    })}
                    {visible.length === 0 && <tr><td colSpan={6} className="empty-row">No files match this filter.</td></tr>}
                  </tbody>
                </table>

                {pages > 1 && (
                  <div className="pagination">
                    <button type="button" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>Previous</button>
                    <span>Page {safePage + 1} of {pages}</span>
                    <button type="button" disabled={safePage + 1 >= pages} onClick={() => setPage(safePage + 1)}>Next</button>
                  </div>
                )}
              </div>
            </div>

            <div className="manifest-confirmation">
              <label>
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy || scanning}
                  onChange={(event) => onConfirm(event.target.checked)}
                />
                <span>I confirm these are the intended source and reference inputs.</span>
              </label>
              <div className="start-review-area">
                {issues.length > 0 ? (
                  <ul className="validation-list" aria-label="Manifest issues">
                    {issues.map((issue) => <li key={issue}>{issue}</li>)}
                  </ul>
                ) : (
                  <p>Ready to upload this manifest and start deterministic backend processing.</p>
                )}
                <button className="button button-primary button-start" type="button" disabled={!canStart} onClick={onStart}>
                  {busy ? uploadProgress ? `Uploading ${uploadProgress.percentage}%…` : "Preparing upload…" : "Start review"}
                </button>
              </div>
            </div>
            {busy && (
              <div className="upload-progress" role="status" aria-live="polite">
                {uploadProgress ? (
                  <>
                    <progress max={100} value={uploadProgress.percentage} aria-label="Measured request upload progress" />
                    <span>
                      Measured HTTP upload: {uploadProgress.percentage}% · {formatBytes(uploadProgress.loadedBytes)} of {formatBytes(uploadProgress.totalBytes)}
                    </span>
                  </>
                ) : (
                  <span>Preparing the multipart request. No upload percentage is shown until the browser reports measured bytes.</span>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function purposesFor(entry: InventoryEntry, profile: CapabilityProfile | undefined): FilePurpose[] {
  if (!profile) return entry.purpose ? [entry.purpose] : [];
  const dot = entry.filename.lastIndexOf(".");
  const extension = dot >= 0 ? entry.filename.slice(dot).toLowerCase() : "";
  const purposes: FilePurpose[] = [];
  if (profile.source.formats.some((format) => format.extension.toLowerCase() === extension)) purposes.push("SOURCE");
  if (profile.reference.formats.some((format) => format.extension.toLowerCase() === extension)) purposes.push("REFERENCE");
  return purposes;
}
