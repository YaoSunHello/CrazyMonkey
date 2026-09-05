import { useEffect, useId, useMemo, useRef, useState } from "react";
import "./pack.css";

type JobState = "QUEUED" | "PROCESSING" | "COMPLETED" | "COMPLETED_WITH_ISSUES" | "FAILED";
type CheckState = "PASS" | "FAIL" | "UNRESOLVED" | "CANNOT_VERIFY";

interface ModelConfig {
  configured?: boolean;
  provider?: string | null;
  model?: string | null;
}

interface WorkflowOption {
  id: string;
  label: string;
  description: string;
  requiresWorkbook: boolean;
  requiresModel: boolean;
}

interface StatementConfig {
  backendReachable: boolean;
  llmConfigured: boolean;
  daytonaConfigured: boolean;
  model?: ModelConfig | null;
  workflows?: WorkflowOption[];
}

interface ProfileSummary {
  id: string;
  label: string;
  description: string;
}

interface StatementCheck {
  name: string;
  status: CheckState;
  message?: string;
  detail?: string;
  evidence?: unknown;
}

interface StatementRow {
  bankReference?: string;
  valueDate?: string;
  postDate?: string;
  credit?: string | number | null;
  debit?: string | number | null;
  balance?: string | number | null;
  currency?: string;
  narrative?: string;
  citation?: string;
  provenance?: { page?: number; x0?: number; top?: number; x1?: number; bottom?: number };
}

interface StatementFileResult {
  fileId: string;
  clientFileId?: string;
  relativePath: string;
  role: "BANK_STATEMENT" | "REFERENCE_WORKBOOK" | string;
  sourceSha256?: string;
  status: string;
  summary?: string;
  account?: string;
  accountNumber?: string;
  currency?: string;
  closingBalance?: string | number | null;
  rowCount?: number;
  checks?: StatementCheck[];
  rows?: StatementRow[];
  error?: string | null;
}

interface StatementJob {
  jobId: string;
  state: JobState;
  workflowId: string;
  fileCount: number;
  processedFiles: number;
  createdAt?: string;
  completedAt?: string | null;
  timeline?: Array<{ state: JobState; at: string }>;
  modelRequested?: boolean;
  modelCallAttempted?: boolean;
  modelCallSucceeded?: boolean | null;
  modelError?: string | null;
  runIds?: string[];
  files: StatementFileResult[];
  artifacts?: Array<{
    id: string;
    filename: string;
    kind?: string;
    downloadUrl: string;
  }>;
  error?: string | null;
}

interface SelectedSource {
  file: File;
  relativePath: string;
  clientFileId: string;
  role: "BANK_STATEMENT" | "REFERENCE_WORKBOOK";
}

export interface StatementWorkspaceProps {
  baseUrl?: string;
}

const activeStates = new Set<JobState>(["QUEUED", "PROCESSING"]);
const terminalLabels: Record<JobState, string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing original files",
  COMPLETED: "Completed",
  COMPLETED_WITH_ISSUES: "Completed — review issues found",
  FAILED: "Failed",
};
const deterministicWorkflow: WorkflowOption = {
  id: "statement-validation",
  label: "Validate statement arithmetic",
  description: "Parse the original PDF and run the deterministic balance, row-count and source-provenance checks. No model or reference workbook is used.",
  requiresWorkbook: false,
  requiresModel: false,
};
const ignoredFolders = new Set(["__macosx", "__pycache__", "node_modules", ".cache", "cache", "tmp", "temp"]);
const maxFileBytes = 25 * 1024 * 1024;
const maxBatchBytes = 100 * 1024 * 1024;
const directoryAttributes = { webkitdirectory: "", directory: "" };
const activeJobStorageKey = "crazymonkey.statement-job-id";

function apiRoot(value: string) {
  return value.replace(/\/+$/, "");
}

async function readJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Backend unavailable. Check that the CrazyMonkey backend is running, then try again.", { cause: error });
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail.length <= 500) detail = ` ${body.detail}`;
    } catch {
      // A status code is still actionable when an upstream proxy returns HTML.
    }
    throw new Error(`The backend rejected this request (HTTP ${response.status}).${detail}`);
  }
  try {
    return await response.json() as T;
  } catch {
    throw new Error("The backend returned an unreadable response.");
  }
}

function randomId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function fileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}

function roleLabel(role: string) {
  return role === "REFERENCE_WORKBOOK" ? "Reference workbook" : role === "BANK_STATEMENT" ? "Bank statement" : role.replaceAll("_", " ").toLowerCase();
}

function checkLabel(name: string) {
  return name.replaceAll("_", " ").replace(/^./, value => value.toUpperCase());
}

function statusClass(state: string) {
  return state.toLowerCase().replaceAll("_", "-");
}

function readableEvidence(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(readableEvidence).filter(Boolean).join("\n");
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const preferred = ["equation", "expected", "actual", "delta", "citation", "source", "detail"]
      .filter(key => record[key] !== undefined)
      .map(key => `${key.replaceAll("_", " ")}: ${readableEvidence(record[key])}`);
    return preferred.length ? preferred.join(" · ") : Object.entries(record).map(([key, item]) => `${key}: ${readableEvidence(item)}`).join(" · ");
  }
  return String(value);
}

function rowCitation(row: StatementRow) {
  if (row.citation) return row.citation;
  const p = row.provenance;
  if (!p?.page) return "Source location unavailable";
  const box = [p.x0, p.top, p.x1, p.bottom].every(value => typeof value === "number")
    ? ` @ (${Math.round(p.x0!)},${Math.round(p.top!)})–(${Math.round(p.x1!)},${Math.round(p.bottom!)})`
    : "";
  return `Page ${p.page}${box}`;
}

function rememberJob(jobId?: string) {
  try {
    if (jobId) window.sessionStorage.setItem(activeJobStorageKey, jobId);
    else window.sessionStorage.removeItem(activeJobStorageKey);
  } catch {
    // Storage can be disabled; the live job still remains available in this tab.
  }
}

export function StatementWorkspace({
  baseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
}: StatementWorkspaceProps) {
  const api = apiRoot(baseUrl);
  const fileInputId = useId();
  const folderInputId = useId();
  const workflowId = useId();
  const instructionId = useId();
  const submitGuard = useRef(false);
  const requestId = useRef<string | null>(null);
  const [config, setConfig] = useState<StatementConfig | null>(null);
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [configError, setConfigError] = useState<string | null>(null);
  const [selectedWorkflow, setSelectedWorkflow] = useState("statement-validation");
  const [selectedFiles, setSelectedFiles] = useState<SelectedSource[]>([]);
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("What is wrong with these bank statements?");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [job, setJob] = useState<StatementJob | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [refreshConfig, setRefreshConfig] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    Promise.all([
      readJson<StatementConfig>(`${api}/api/v1/statement-jobs/config`, { signal: controller.signal }),
      readJson<ProfileSummary[]>(`${api}/api/profiles`, { signal: controller.signal }),
    ]).then(([nextConfig, nextProfiles]) => {
      if (!current) return;
      if (nextConfig.backendReachable !== true) throw new Error("The backend health response is incomplete.");
      setConfig(nextConfig);
      setProfiles(Array.isArray(nextProfiles) ? nextProfiles : []);
      setConfigError(null);
    }).catch(error => {
      if (!current || (error instanceof DOMException && error.name === "AbortError")) return;
      setConfig(null);
      setProfiles([]);
      setConfigError(error instanceof Error ? error.message : "Backend unavailable.");
    });
    return () => { current = false; controller.abort(); };
  }, [api, refreshConfig]);

  useEffect(() => {
    let savedJobId: string | null = null;
    try { savedJobId = window.sessionStorage.getItem(activeJobStorageKey); }
    catch { return; }
    if (!savedJobId) return;
    const controller = new AbortController();
    let current = true;
    void readJson<StatementJob>(
      `${api}/api/v1/statement-jobs/${encodeURIComponent(savedJobId)}`,
      { signal: controller.signal },
    ).then(recovered => {
      if (!current || recovered.jobId !== savedJobId) return;
      setJob(recovered);
      setSelectedWorkflow(recovered.workflowId);
      setPollError(null);
    }).catch(error => {
      if (!current || (error instanceof DOMException && error.name === "AbortError")) return;
      setPollError(error instanceof Error ? `Saved job could not be restored. ${error.message}` : "Saved job could not be restored.");
    });
    return () => { current = false; controller.abort(); };
  }, [api]);

  const activeJobId = job?.jobId;
  const activeJobState = job?.state;
  useEffect(() => {
    if (!activeJobId || !activeJobState || !activeStates.has(activeJobState)) return;
    const controller = new AbortController();
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await readJson<StatementJob>(`${api}/api/v1/statement-jobs/${encodeURIComponent(activeJobId)}`, { signal: controller.signal });
        if (!current) return;
        if (!next.jobId || next.jobId !== activeJobId) throw new Error("The backend returned the wrong job.");
        setJob(next);
        setPollError(null);
        if (activeStates.has(next.state)) timer = setTimeout(() => void poll(), 750);
      } catch (error) {
        if (!current || (error instanceof DOMException && error.name === "AbortError")) return;
        setPollError(error instanceof Error ? error.message : "The processing status could not be refreshed.");
        timer = setTimeout(() => void poll(), 2500);
      }
    };
    timer = setTimeout(() => void poll(), 250);
    return () => { current = false; controller.abort(); if (timer) clearTimeout(timer); };
  }, [api, activeJobId, activeJobState]);

  const workflows = useMemo(() => {
    const fromBackend = config?.workflows?.filter(item => item && typeof item.id === "string") ?? [];
    const byId = new Map<string, WorkflowOption>([[deterministicWorkflow.id, deterministicWorkflow]]);
    for (const profile of profiles.filter(item => item.id === "journal-entries" || item.id === "pipeline-validation")) {
      byId.set(profile.id, {
        id: profile.id,
        label: profile.label,
        description: profile.description,
        requiresWorkbook: true,
        requiresModel: true,
      });
    }
    for (const item of fromBackend) byId.set(item.id, item);
    return [...byId.values()];
  }, [config?.workflows, profiles]);

  const workflow = workflows.find(item => item.id === selectedWorkflow) ?? deterministicWorkflow;
  const pdfs = selectedFiles.filter(item => item.role === "BANK_STATEMENT");
  const workbooks = selectedFiles.filter(item => item.role === "REFERENCE_WORKBOOK");
  const totalBytes = selectedFiles.reduce((total, item) => total + item.file.size, 0);
  const jobActive = Boolean(job && activeStates.has(job.state));
  const startIssue = (() => {
    if (configError || !config?.backendReachable) return "Backend unavailable.";
    if (pdfs.length === 0) return "Add at least one bank statement PDF.";
    if (selectedFiles.length > 40) return "A job can contain at most 40 files.";
    if (totalBytes > maxBatchBytes) return "The selected files exceed the 100 MB job limit.";
    if (workflow.requiresWorkbook && workbooks.length === 0) return "This workflow also needs the supplied reference workbook (.xlsx).";
    if (workflow.requiresWorkbook && workbooks.length > 1) return "Choose exactly one reference workbook for this workflow.";
    if (!workflow.requiresWorkbook && workbooks.length > 0) return "Remove the reference workbook or choose a journal-entry workflow.";
    if (workflow.requiresModel && !config.llmConfigured) return "The backend model is not configured. Choose deterministic statement validation or configure the backend.";
    if (workflow.requiresModel && !config.daytonaConfigured) return "The backend sandbox is not configured. Choose deterministic statement validation or configure Daytona.";
    return null;
  })();

  function addFiles(list: FileList | null) {
    if (submitting || jobActive) return;
    const incoming = Array.from(list ?? []);
    const accepted: SelectedSource[] = [];
    const skipped: string[] = [];
    const known = new Set(selectedFiles.map(item => `${item.relativePath}\u0000${item.file.size}`));
    for (const file of incoming) {
      const relativePath = (file.webkitRelativePath || file.name).replaceAll("\\", "/").replace(/^\/+/, "");
      const parts = relativePath.split("/");
      const base = parts.at(-1) ?? file.name;
      const extension = base.split(".").pop()?.toLowerCase();
      if (parts.some(part => part.startsWith(".") || ignoredFolders.has(part.toLowerCase()))) {
        skipped.push(`${relativePath} (hidden/cache folder)`);
        continue;
      }
      if (/^readme(?:\.|$)/i.test(base)) {
        skipped.push(`${relativePath} (README is not source evidence)`);
        continue;
      }
      if (extension !== "pdf" && extension !== "xlsx") {
        skipped.push(`${relativePath} (unsupported type)`);
        continue;
      }
      if (file.size > maxFileBytes) {
        skipped.push(`${relativePath} (over 25 MB)`);
        continue;
      }
      const key = `${relativePath}\u0000${file.size}`;
      if (known.has(key)) {
        skipped.push(`${relativePath} (already selected)`);
        continue;
      }
      known.add(key);
      accepted.push({
        file,
        relativePath,
        clientFileId: randomId(),
        role: extension === "pdf" ? "BANK_STATEMENT" : "REFERENCE_WORKBOOK",
      });
    }
    setSelectedFiles(previous => [...previous, ...accepted]);
    requestId.current = null;
    setJob(null);
    rememberJob();
    setSubmitError(null);
    setSelectionNotice(skipped.length ? `${skipped.length} file${skipped.length === 1 ? " was" : "s were"} skipped: ${skipped.join("; ")}.` : accepted.length ? `${accepted.length} source file${accepted.length === 1 ? "" : "s"} ready. Nothing has started yet.` : null);
  }

  function removeFile(clientFileId: string) {
    setSelectedFiles(previous => previous.filter(item => item.clientFileId !== clientFileId));
    requestId.current = null;
    setJob(null);
    rememberJob();
  }

  function changeWorkflow(value: string) {
    if (submitting || jobActive) return;
    setSelectedWorkflow(value);
    requestId.current = null;
    setJob(null);
    rememberJob();
    setSubmitError(null);
  }

  async function startJob() {
    if (startIssue || submitting || submitGuard.current) return;
    submitGuard.current = true;
    setSubmitting(true);
    setSubmitError(null);
    setPollError(null);
    requestId.current ||= randomId();
    const body = new FormData();
    body.append("workflowId", workflow.id);
    body.append("clientRequestId", requestId.current);
    body.append("instruction", instruction.trim() || "What is wrong with these bank statements?");
    const manifest = selectedFiles.map(item => ({
      clientFileId: item.clientFileId,
      filename: item.file.name,
      relativePath: item.relativePath,
      role: item.role,
    }));
    for (const item of selectedFiles) {
      body.append("files", item.file, item.file.name);
      body.append("fileIds", item.clientFileId);
    }
    body.append("manifest", JSON.stringify(manifest));
    try {
      const next = await readJson<StatementJob>(`${api}/api/v1/statement-jobs`, { method: "POST", body });
      if (!next.jobId || !next.state) throw new Error("The backend did not return a valid processing job.");
      setJob(next);
      rememberJob(next.jobId);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "The processing job could not be started.");
    } finally {
      submitGuard.current = false;
      setSubmitting(false);
    }
  }

  const processed = job?.processedFiles ?? 0;
  const fileCount = job?.fileCount ?? selectedFiles.length;
  const percent = fileCount ? Math.min(100, Math.round(processed / fileCount * 100)) : 0;
  const finished = Boolean(job && !activeStates.has(job.state));
  const failedChecks = job?.files.flatMap(file => file.checks ?? []).filter(check => check.status === "FAIL").length ?? 0;
  const reviewChecks = job?.files.flatMap(file => file.checks ?? []).filter(check => check.status === "UNRESOLVED" || check.status === "CANNOT_VERIFY").length ?? 0;
  const resultArtifact = job?.artifacts?.find(artifact => artifact.id === "result-json");
  const resultDownloadUrl = resultArtifact?.downloadUrl
    ? /^https?:\/\//i.test(resultArtifact.downloadUrl)
      ? resultArtifact.downloadUrl
      : `${api}${resultArtifact.downloadUrl.startsWith("/") ? "" : "/"}${resultArtifact.downloadUrl}`
    : null;
  const modelStatus = !job?.modelRequested
    ? { text: "Not used by this workflow", tone: "is-ready" }
    : job.modelCallSucceeded === true
      ? { text: "Succeeded", tone: "is-ready" }
      : job.modelCallSucceeded === false || job.state === "FAILED"
        ? { text: "Failed — no fallback result was substituted", tone: "is-blocked" }
        : job.modelCallAttempted
          ? { text: "In progress", tone: "is-running" }
          : { text: "Waiting to start", tone: "is-running" };

  return (
    <section className="pack-workspace statement-workspace page-enter" aria-labelledby="statement-heading">
      <header className="pack-heading">
        <div>
          <p className="eyebrow">Original-file processing</p>
          <h1 id="statement-heading" tabIndex={-1}>Check bank statements with the real pipeline.</h1>
          <p>Upload the original PDFs, choose what you want to run, and follow every document through parsing and deterministic verification.</p>
        </div>
        <div className="statement-health" aria-label="Backend status">
          <span className={`pack-connection ${config?.backendReachable ? "is-configured" : ""}`}>{config?.backendReachable ? "Backend connected" : configError ? "Backend unavailable" : "Checking backend…"}</span>
          {configError && <button type="button" className="pack-text-button" onClick={() => setRefreshConfig(value => value + 1)}>Retry connection</button>}
        </div>
      </header>

      <div className="pack-scope-note">
        <strong>No NAV-document guessing. No fixture fallback.</strong>
        <p>PDFs are treated as bank statements; an XLSX is treated as a reference workbook only when the selected workflow requires one. Results below come from the uploaded bytes and link back to those exact source files.</p>
      </div>

      <div className="statement-service-grid" aria-label="Processing services">
        <div className={config?.backendReachable ? "is-ready" : "is-blocked"}><strong>Backend</strong><span>{config?.backendReachable ? "Reachable" : "Unavailable"}</span></div>
        <div className={config?.backendReachable ? "is-ready" : "is-blocked"}><strong>Parser + verifier</strong><span>{config?.backendReachable ? "Ready" : "Waiting for backend"}</span></div>
        <div className={config?.llmConfigured ? "is-ready" : "is-blocked"}><strong>Live model</strong><span>{config?.llmConfigured ? `Configured${config.model?.model ? ` · ${config.model.model}` : ""}` : "Not configured"}</span></div>
        <div className={config?.daytonaConfigured ? "is-ready" : "is-blocked"}><strong>Sandbox</strong><span>{config?.daytonaConfigured ? "Configured" : "Not configured"}</span></div>
      </div>

      {configError && <p className="pack-error statement-top-error" role="alert">{configError}</p>}

      <div className="pack-layout">
        <aside className="pack-sidebar">
          <section className="pack-panel" aria-labelledby="statement-workflow-heading">
            <h2 id="statement-workflow-heading">1. Choose a workflow</h2>
            <label className="pack-instruction-label" htmlFor={workflowId}>Processing workflow</label>
            <select id={workflowId} className="statement-select" value={selectedWorkflow} onChange={event => changeWorkflow(event.target.value)} disabled={!config || submitting || jobActive}>
              {workflows.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <p className="pack-muted statement-workflow-description">{workflow.description}</p>
            <ul className="statement-requirements">
              <li>Required: one or more text-based statement PDFs</li>
              <li>{workflow.requiresWorkbook ? "Required: exactly one reference XLSX" : "Reference workbook: not used"}</li>
              <li>{workflow.requiresModel ? "Execution: live model + isolated sandbox" : "Execution: deterministic parser + checks"}</li>
            </ul>
          </section>

          <section className="pack-panel" aria-labelledby="statement-files-heading">
            <h2 id="statement-files-heading">2. Add original files</h2>
            <p className="pack-muted">Choose files directly or select a folder. Folder selection only prepares the list; it never starts processing.</p>
            <div className="pack-select-actions">
              <input id={fileInputId} className="visually-hidden" type="file" multiple accept=".pdf,.xlsx" aria-label="Select bank statement files" disabled={submitting || jobActive} onChange={event => { addFiles(event.target.files); event.target.value = ""; }} />
              <label className="button button-primary" aria-disabled={submitting || jobActive} htmlFor={fileInputId}>Add files</label>
              <input id={folderInputId} className="visually-hidden" type="file" multiple {...directoryAttributes} aria-label="Select bank statement folder" disabled={submitting || jobActive} onChange={event => { addFiles(event.target.files); event.target.value = ""; }} />
              <label className="button button-secondary" aria-disabled={submitting || jobActive} htmlFor={folderInputId}>Select folder</label>
            </div>
            <p className="pack-file-types">PDF statements · XLSX reference workbook<br />README, hidden, cache, temporary and unsupported files are skipped.</p>
            {selectionNotice && <p className="pack-notice" role="status">{selectionNotice}</p>}
            {selectedFiles.length > 0 && <>
              <div className="pack-selection-heading"><strong>{selectedFiles.length} files · {fileSize(totalBytes)}</strong><button type="button" className="pack-text-button" disabled={submitting || jobActive} onClick={() => { setSelectedFiles([]); setSelectionNotice(null); setJob(null); setPollError(null); requestId.current = null; rememberJob(); }}>Clear</button></div>
              <ul className="pack-selected-files" aria-label="Original files selected for processing">
                {selectedFiles.map(item => <li key={item.clientFileId}>
                  <span title={item.relativePath}>{item.relativePath}<small>{roleLabel(item.role)} · {fileSize(item.file.size)}</small></span>
                  <button type="button" className="pack-remove" aria-label={`Remove ${item.relativePath}`} disabled={submitting || jobActive} onClick={() => removeFile(item.clientFileId)}>×</button>
                </li>)}
              </ul>
            </>}
          </section>

          <section className="pack-panel" aria-labelledby="statement-start-heading">
            <h2 id="statement-start-heading">3. Process</h2>
            <label className="pack-instruction-label" htmlFor={instructionId}>Review instruction</label>
            <textarea id={instructionId} value={instruction} onChange={event => setInstruction(event.target.value)} rows={3} disabled={submitting || jobActive} />
            <p className="pack-small pack-muted">Deterministic validation reports statement arithmetic and source support. Model-backed workflows use this instruction without falling back to a fixture.</p>
            <button type="button" className="button button-primary pack-start" disabled={Boolean(startIssue) || submitting || jobActive} onClick={() => void startJob()}>
              {submitting ? "Uploading original files…" : `Start processing${pdfs.length ? ` ${pdfs.length} statement${pdfs.length === 1 ? "" : "s"}` : ""}`}
            </button>
            {startIssue && <p className="pack-small pack-muted">{startIssue}</p>}
            {submitError && <p className="pack-error" role="alert">{submitError}</p>}
          </section>
        </aside>

        <section className="pack-results" aria-labelledby="statement-results-heading">
          <div className="pack-results-heading">
            <div><p className="eyebrow">Live job</p><h2 id="statement-results-heading">Processing and results</h2></div>
            {job && <span className={`pack-status pack-status-${statusClass(job.state)}`}>{terminalLabels[job.state] ?? job.state}</span>}
          </div>

          {!job && <div className="pack-empty"><span aria-hidden="true">↳</span><h3>No job has started.</h3><p>Choose the statement-validation workflow, add the two Calder PDFs, then start processing. The backend will return a real job ID before work begins.</p></div>}

          {job && <>
            <p className="pack-run-id"><strong>Job ID:</strong> {job.jobId}{job.runIds?.length ? ` · engine run ${job.runIds.join(", ")}` : ""}</p>
            <div className="pack-metrics">
              <div><strong>{processed}/{fileCount}</strong><span>files processed</span></div>
              <div><strong>{failedChecks}</strong><span>failed checks</span></div>
              <div><strong>{reviewChecks}</strong><span>review items</span></div>
            </div>
            <div className="pack-progress" role="progressbar" aria-label="Original files processed" aria-valuemin={0} aria-valuemax={fileCount} aria-valuenow={processed}><span style={{ width: `${percent}%` }} /></div>

            {(job.timeline?.length ?? 0) > 0 && <ol className="statement-timeline" aria-label="Actual job lifecycle">
              {job.timeline!.map((event, index) => <li key={`${event.state}-${event.at}-${index}`}><span aria-hidden="true" /><strong>{terminalLabels[event.state] ?? event.state}</strong><time dateTime={event.at}>{new Date(event.at).toLocaleTimeString("en-GB")}</time></li>)}
            </ol>}

            {activeStates.has(job.state) && <div className="statement-processing" role="status"><span className="statement-spinner" aria-hidden="true" /><div><strong>{terminalLabels[job.state]}</strong><p>{job.state === "QUEUED" ? "The upload is saved. Waiting for a worker…" : "Reading the uploaded PDFs and running the selected checks…"}</p></div></div>}
            {pollError && <p className="pack-error" role="alert">{pollError} The browser will keep retrying this job.</p>}
            {(job.error || job.modelError) && <p className="pack-error" role="alert">{job.error || job.modelError}</p>}

            {job.modelCallAttempted !== undefined && <div className={`statement-model-result ${modelStatus.tone}`}><strong>Model call</strong><span>{modelStatus.text}</span></div>}

            <div className="pack-file-results">
              {job.files.map(file => {
                const checks = file.checks ?? [];
                const failures = checks.filter(check => check.status === "FAIL");
                const reviewItems = checks.filter(check => check.status === "UNRESOLVED" || check.status === "CANNOT_VERIFY");
                const sourceUrl = `${api}/api/v1/statement-jobs/${encodeURIComponent(job.jobId)}/sources/${encodeURIComponent(file.fileId)}`;
                return <article className="pack-file-card statement-file-card" key={file.fileId || file.relativePath}>
                  <header><div><span className="pack-extension">{file.relativePath.split(".").pop()?.toUpperCase()}</span><div><h3>{file.relativePath}</h3><p className="pack-extraction">{roleLabel(file.role)} · {file.status}</p></div></div><a className="statement-source-link" href={sourceUrl} target="_blank" rel="noreferrer">Open source ↗</a></header>
                  {file.sourceSha256 && <p className="statement-hash" title={file.sourceSha256}>Source SHA-256: {file.sourceSha256.slice(0, 16)}…</p>}
                  {file.error && <p className="pack-error" role="alert">{file.error}</p>}
                  {file.summary && <p className="pack-file-summary">{file.summary}</p>}
                  {file.role === "BANK_STATEMENT" && <div className="statement-file-metrics">
                    <span><strong>{file.account || file.accountNumber || "—"}</strong>account</span>
                    <span><strong>{file.currency || "—"}</strong>currency</span>
                    <span><strong>{typeof file.rowCount === "number" ? file.rowCount.toLocaleString("en-GB") : "—"}</strong>rows</span>
                    <span><strong>{file.closingBalance ?? "—"}</strong>closing balance</span>
                  </div>}
                  {checks.length > 0 && <section className="statement-checks" aria-label={`Verification checks for ${file.relativePath}`}>
                    <h4>Verification checks</h4>
                    <ul>{checks.map((check, index) => {
                      const evidence = readableEvidence(check.evidence);
                      return <li className={`statement-check check-${statusClass(check.status)}`} key={`${check.name}-${index}`}>
                        <div><strong>{checkLabel(check.name)}</strong><span>{check.status}</span></div>
                        {(check.message || check.detail) && <p>{check.message || check.detail}</p>}
                        {evidence && <pre>{evidence}</pre>}
                      </li>;
                    })}</ul>
                    {failures.length > 0 && <p className="statement-review-callout"><strong>{failures.length} calculation/structure failure{failures.length === 1 ? "" : "s"} require review.</strong> Expected, actual, delta and statement location are shown above where available.</p>}
                    {reviewItems.length > 0 && <p className="statement-review-callout"><strong>{reviewItems.length} unresolved item{reviewItems.length === 1 ? "" : "s"}.</strong> Missing evidence is not presented as a pass.</p>}
                  </section>}
                  {(file.rows?.length ?? 0) > 0 && <details className="statement-rows"><summary>Parsed source rows ({file.rowCount ?? file.rows!.length})</summary><div className="statement-table-wrap"><table><thead><tr><th>Date</th><th>Reference / narrative</th><th>Credit</th><th>Debit</th><th>Balance</th><th>Source</th></tr></thead><tbody>{file.rows!.slice(0, 12).map((row, index) => <tr key={`${row.bankReference ?? "row"}-${index}`}><td>{row.valueDate || row.postDate || "—"}</td><td><strong>{row.bankReference || "—"}</strong>{row.narrative && <small>{row.narrative}</small>}</td><td>{row.credit ?? "—"}</td><td>{row.debit ?? "—"}</td><td>{row.balance ?? "—"}</td><td><a href={sourceUrl} target="_blank" rel="noreferrer">{rowCitation(row)}</a></td></tr>)}</tbody></table></div>{file.rows!.length > 12 && <p className="pack-small pack-muted">Showing the first 12 rows. Download the raw job record for every parsed row.</p>}</details>}
                </article>;
              })}
            </div>

            {finished && job.state !== "FAILED" && resultDownloadUrl && <div className="statement-download"><div><strong>Raw persisted job record</strong><p>Download the backend job record for this exact run, including every parsed row and source hash. Model workflows additionally pass through their configured output transform.</p></div><a className="button button-primary" href={resultDownloadUrl}>Download JSON</a></div>}
            {finished && <button type="button" className="button button-secondary statement-new-job" onClick={() => { setJob(null); setPollError(null); requestId.current = null; rememberJob(); }}>Process another selection</button>}
          </>}
        </section>
      </div>
    </section>
  );
}
