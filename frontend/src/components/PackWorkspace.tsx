import { useEffect, useId, useRef, useState } from "react";
import "./pack.css";

type RunStatus = "QUEUED" | "INGESTING" | "ANALYSING" | "COMPLETE" | "COMPLETE_WITH_ERRORS" | "FAILED";
interface PackConfig { configured: boolean; provider: string | null; model: string | null }
interface PackFinding { title: string; status?: string; severity: string; explanation: string; evidence_ids: string[] }
interface PackFile {
  relative_path: string; status: RunStatus; row_count?: number; cell_count?: number; page_count?: number;
  summary?: string; role?: string; findings?: PackFinding[]; suggested_actions?: string[]; limitations?: string[]; error?: string | null;
}
interface RunSummary {
  run_id: string; status: RunStatus; file_count?: number; created_at?: string;
  processed_files?: number; model_call_count?: number; elapsed_seconds?: number;
}
interface PackRun extends RunSummary {
  mode: "LIVE_MODEL"; files: PackFile[]; error?: string | null; output_directory?: string;
}
interface SelectedFile { file: File; path: string }
export interface PackWorkspaceProps { baseUrl?: string }

const activeStatuses = new Set<RunStatus>(["QUEUED", "INGESTING", "ANALYSING"]);
const labels: Record<RunStatus, string> = {
  QUEUED: "Queued", INGESTING: "Importing", ANALYSING: "Analysing", COMPLETE: "Complete",
  COMPLETE_WITH_ERRORS: "Complete with errors", FAILED: "Failed",
};
const defaultInstruction = "Review these financial documents, identify material discrepancies and explain findings with source evidence. State any limits or missing evidence.";
const directoryAttributes = { webkitdirectory: "", directory: "" };
const roleLabels: Record<string, string> = { SOURCE: "Source", REFERENCE: "Reference", WORKFLOW_CONTEXT: "Workflow context", UNKNOWN: "Unknown" };

function statusLabel(status: RunStatus) { return labels[status] ?? status; }
function count(value?: number) { return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("en-GB") : "—"; }
function fileSize(bytes: number) { return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.ceil(bytes / 1024))} KB`; }

async function readJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`The backend returned HTTP ${response.status}. The request was not completed.`);
  try { return await response.json() as T; }
  catch { throw new Error("The backend returned an unreadable response."); }
}

export function PackWorkspace({ baseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8012" }: PackWorkspaceProps) {
  const api = baseUrl.replace(/\/+$/, "");
  const folderId = useId();
  const filesId = useId();
  const instructionId = useId();
  const uploadController = useRef<AbortController | null>(null);
  const [config, setConfig] = useState<PackConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [run, setRun] = useState<PackRun | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [instruction, setInstruction] = useState(defaultInstruction);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    void readJson<PackConfig>(`${api}/api/pack/config`, { signal: controller.signal }).then(value => {
      if (typeof value.configured !== "boolean") throw new Error("The backend configuration response is incomplete.");
      if (current) { setConfig(value); setConfigError(null); }
    }).catch(error => { if (current) { setConfig(null); setConfigError(error instanceof Error ? error.message : "Cannot read backend configuration."); } });
    void readJson<{ runs: RunSummary[] }>(`${api}/api/pack/runs`, { signal: controller.signal }).then(value => {
      if (!Array.isArray(value.runs) || value.runs.some(item => typeof item.run_id !== "string")) throw new Error("The saved-run response is incomplete.");
      if (current) {
        setRuns(value.runs); setRunsError(null);
        setSelectedRunId(previous => previous ?? value.runs[0]?.run_id ?? null);
      }
    }).catch(error => { if (current) setRunsError(error instanceof Error ? error.message : "Cannot load saved runs."); });
    return () => { current = false; controller.abort(); };
  }, [api, refresh]);

  useEffect(() => {
    if (!selectedRunId) return;
    const controller = new AbortController();
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const value = await readJson<PackRun>(`${api}/api/pack/runs/${encodeURIComponent(selectedRunId!)}`, { signal: controller.signal });
        if (value.run_id !== selectedRunId || !Array.isArray(value.files) || value.mode !== "LIVE_MODEL") throw new Error("The run response is incomplete or does not describe a live-model run.");
        if (!current) return;
        setRun(value); setRunError(null);
        setRuns(previous => [value, ...previous.filter(item => item.run_id !== value.run_id)]);
        if (activeStatuses.has(value.status)) timer = setTimeout(() => void poll(), 1500);
      } catch (error) {
        if (current) {
          setRunError(error instanceof Error ? error.message : "Cannot refresh this run.");
          timer = setTimeout(() => void poll(), 4000);
        }
      }
    }
    void poll();
    return () => { current = false; controller.abort(); if (timer) clearTimeout(timer); };
  }, [api, selectedRunId, refresh]);

  useEffect(() => () => uploadController.current?.abort(), []);

  function selectFiles(files: FileList | null) {
    const all = Array.from(files ?? []);
    const supported = all.map(file => ({ file, path: (file.webkitRelativePath || file.name).replaceAll("\\", "/") }))
      .filter(item => !item.path.split("/").some(part => part.startsWith(".")) && /\.(xlsx|pdf|md|txt)$/i.test(item.path));
    setSelectedFiles(previous => Array.from(new Map([...previous, ...supported].map(item => [item.path, item])).values()));
    const skipped = all.length - supported.length;
    setSelectionNotice(skipped ? `${skipped} hidden or unsupported ${skipped === 1 ? "file was" : "files were"} skipped.` : null);
  }

  async function submit() {
    if (!config?.configured || !selectedFiles.length || submitting) return;
    const controller = new AbortController();
    uploadController.current = controller;
    setSubmitting(true); setSubmitError(null);
    const body = new FormData();
    selectedFiles.forEach(item => { body.append("files", item.file); body.append("relative_paths", item.path); });
    body.append("instruction", instruction.trim() || defaultInstruction);
    try {
      const value = await readJson<{ run_id: string }>(`${api}/api/pack/runs`, { method: "POST", body, signal: controller.signal });
      if (typeof value.run_id !== "string" || !value.run_id) throw new Error("The backend did not return a run identifier.");
      setRun(null); setRunError(null); setSelectedRunId(value.run_id);
    } catch (error) {
      if (!controller.signal.aborted) setSubmitError(error instanceof Error ? error.message : "The import could not be started.");
    } finally {
      if (!controller.signal.aborted) setSubmitting(false);
    }
  }

  const visibleRun = run?.run_id === selectedRunId ? run : null;
  const totalBytes = selectedFiles.reduce((sum, item) => sum + item.file.size, 0);
  const processed = visibleRun?.processed_files ?? 0;
  const total = visibleRun?.file_count ?? 0;
  const progressPercent = total ? Math.min(100, Math.max(0, processed / total * 100)) : 0;

  return (
    <section className="pack-workspace page-enter" aria-labelledby="pack-heading">
      <header className="pack-heading">
        <div><p className="eyebrow">Financial document workspace</p><h1 id="pack-heading">Bring the whole dataset.</h1>
          <p>Import workbooks, PDFs and supporting notes. Follow each file from extraction through model review.</p></div>
        <span className={`pack-connection ${config?.configured ? "is-configured" : ""}`}>
          {config?.configured ? "Model configured on backend" : configError ? "Backend unavailable" : config ? "Model configuration needed" : "Checking backend…"}
        </span>
      </header>
      <div className="pack-scope-note"><strong>Full files imported. Model review uses bounded excerpts.</strong>
        <p>Extraction counts describe the imported data. The model reviews selected content, so a completed run does not establish that every row, cell or page was checked. Review each file’s limitations and source evidence.</p></div>
      <div className="pack-layout">
        <aside className="pack-sidebar">
          <section className="pack-panel" aria-labelledby="pack-import-heading">
            <h2 id="pack-import-heading">Import a dataset</h2>
            <p className="pack-muted">Select a folder to include its subfolders, or add individual files.</p>
            <div className="pack-select-actions">
              <input className="visually-hidden" id={folderId} type="file" multiple {...directoryAttributes} aria-label="Select dataset folder"
                onChange={event => { selectFiles(event.target.files); event.target.value = ""; }} />
              <label className="button button-primary" htmlFor={folderId}>Select folder</label>
              <input className="visually-hidden" id={filesId} type="file" multiple accept=".xlsx,.pdf,.md,.txt" aria-label="Select dataset files"
                onChange={event => { selectFiles(event.target.files); event.target.value = ""; }} />
              <label className="button button-secondary" htmlFor={filesId}>Add files</label>
            </div>
            <p className="pack-file-types">XLSX · PDF · Markdown · text<br />Hidden files are skipped.</p>
            {selectionNotice && <p className="pack-notice" role="status">{selectionNotice}</p>}
            {selectedFiles.length > 0 && <>
              <div className="pack-selection-heading"><strong>{selectedFiles.length} files · {fileSize(totalBytes)}</strong>
                <button className="pack-text-button" type="button" onClick={() => { setSelectedFiles([]); setSelectionNotice(null); }} disabled={submitting}>Clear</button></div>
              <ul className="pack-selected-files" aria-label="Files selected for import">{selectedFiles.map(item => <li key={item.path}>
                <span title={item.path}>{item.path}<small>{fileSize(item.file.size)}</small></span>
                <button type="button" className="pack-remove" aria-label={`Remove ${item.path}`} disabled={submitting}
                  onClick={() => setSelectedFiles(previous => previous.filter(file => file.path !== item.path))}>×</button>
              </li>)}</ul>
            </>}
            <label className="pack-instruction-label" htmlFor={instructionId}>Review instruction</label>
            <textarea id={instructionId} value={instruction} onChange={event => setInstruction(event.target.value)} rows={4} maxLength={10000} disabled={submitting} />
            {configError && <p className="pack-error" role="alert">Cannot connect to the model configuration service. {configError}</p>}
            {config && !config.configured && <p className="pack-notice">Configure the model on the backend to start a live review. Saved runs remain available below.</p>}
            {config?.configured && <p className="pack-provider">{config.provider || "Configured provider"}{config.model ? ` · ${config.model}` : ""}</p>}
            {submitError && <p className="pack-error" role="alert">Import failed. {submitError}</p>}
            <button type="button" className="button button-primary pack-start" disabled={!config?.configured || !selectedFiles.length || submitting} onClick={() => void submit()} aria-busy={submitting}>
              {submitting ? "Uploading files…" : `Import and analyse${selectedFiles.length ? ` ${selectedFiles.length} ${selectedFiles.length === 1 ? "file" : "files"}` : ""}`}
            </button>
            <p className="pack-muted pack-small">This starts a real model review using the backend’s configured provider.</p>
          </section>
          <section className="pack-panel" aria-labelledby="pack-runs-heading">
            <div className="pack-selection-heading"><h2 id="pack-runs-heading">Saved runs</h2><button className="pack-text-button" type="button" onClick={() => setRefresh(value => value + 1)}>Refresh</button></div>
            {runsError && <p className="pack-error" role="alert">Cannot load saved runs. {runsError}</p>}
            {!runs.length && !runsError && <p className="pack-muted">No saved runs loaded yet.</p>}
            <ul className="pack-run-list">{runs.map(item => <li key={item.run_id}><button type="button" aria-current={selectedRunId === item.run_id ? "true" : undefined}
              onClick={() => { setSelectedRunId(item.run_id); setRunError(null); }}>
              <strong>{item.run_id}</strong><span>{statusLabel(item.status)} · {count(item.file_count)} files</span>
              {item.created_at && <small>{new Date(item.created_at).toLocaleString("en-GB")}</small>}
            </button></li>)}</ul>
          </section>
        </aside>
        <section className="pack-results" aria-labelledby="pack-results-heading">
          <div className="pack-results-heading"><div><p className="eyebrow">File by file</p><h2 id="pack-results-heading">{visibleRun ? "Dataset review" : "Your review appears here"}</h2></div>
            {visibleRun && <span className={`pack-status pack-status-${visibleRun.status.toLowerCase()}`}>{statusLabel(visibleRun.status)}</span>}</div>
          {runError && <p className="pack-error" role="alert">Cannot refresh this run. {runError}{visibleRun ? " The last received status is shown below." : ""}</p>}
          {!visibleRun && <div className="pack-empty"><span aria-hidden="true">↗</span><h3>{selectedRunId ? "Loading the selected run…" : "Start with the dataset folder"}</h3><p>Saved runs also appear here, including imports started directly through the local backend.</p></div>}
          {visibleRun && <>
            <p className="pack-run-id">Run <code>{visibleRun.run_id}</code> · live-model review</p>
            <div className="pack-metrics"><div><strong>{count(processed)} / {count(total)}</strong><span>Files processed</span></div>
              <div><strong>{count(visibleRun.model_call_count)}</strong><span>Model calls recorded</span></div>
              <div><strong>{typeof visibleRun.elapsed_seconds === "number" ? `${visibleRun.elapsed_seconds.toFixed(1)}s` : "—"}</strong><span>Elapsed time</span></div></div>
            <div className="pack-progress" role="progressbar" aria-label="Files processed" aria-valuemin={0} aria-valuemax={total || 1} aria-valuenow={Math.min(processed, total)}><span style={{ width: `${progressPercent}%` }} /></div>
            {visibleRun.error && <p className="pack-error" role="alert">{visibleRun.error}</p>}
            <div className="pack-file-results">{visibleRun.files.map(file => <article className="pack-file-card" key={file.relative_path}>
              <header><div><span className="pack-extension">{file.relative_path.split(".").pop()?.toUpperCase()}</span><h3>{file.relative_path}</h3></div>
                <span className={`pack-status pack-status-${file.status.toLowerCase()}`}>{statusLabel(file.status)}</span></header>
              <p className="pack-extraction">Extracted: {count(file.row_count)} rows · {count(file.cell_count)} cells · {count(file.page_count)} pages</p>
              {file.summary && <p className="pack-file-summary">{file.summary}</p>}
              {file.error && <p className="pack-error" role="alert">{file.error}</p>}
              {(file.findings?.length || file.limitations?.length || file.suggested_actions?.length || file.role) ? <details className="pack-findings" open={file.status === "FAILED"}>
                <summary>Findings and review limits ({file.findings?.length ?? 0} {file.findings?.length === 1 ? "finding" : "findings"})</summary>
                {file.role && <p className="pack-document-role">Document role: <strong>{roleLabels[file.role] || file.role}</strong></p>}
                {file.findings?.map((finding, index) => <div className="pack-finding" key={`${finding.title}-${index}`}>
                  <div><strong>{finding.title}</strong><span>{finding.severity}{finding.status ? ` · ${finding.status}` : ""}</span></div><p>{finding.explanation}</p>
                  {finding.evidence_ids?.length > 0 && <p className="pack-evidence">Source evidence: {finding.evidence_ids.map(id =>
                    <a key={id} href={`${api}/api/pack/runs/${encodeURIComponent(visibleRun.run_id)}/evidence/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer" title="Open source evidence in a new tab"><code>{id}</code></a>)}</p>}
                </div>)}
                {file.suggested_actions?.length ? <div className="pack-suggested-actions"><strong>Suggested next steps</strong><ol>{file.suggested_actions.map((action, index) => <li key={index}>{action}</li>)}</ol></div> : null}
                {file.limitations?.length ? <div className="pack-limitations"><strong>Review limits</strong><ul>{file.limitations.map((limit, index) => <li key={index}>{limit}</li>)}</ul></div> : null}
              </details> : file.status === "COMPLETE" ? <p className="pack-muted pack-small">No findings were returned for the reviewed content. This does not certify the whole file.</p> : null}
            </article>)}</div>
            {visibleRun.output_directory && <p className="pack-output">Saved locally: <code>{visibleRun.output_directory}</code></p>}
          </>}
        </section>
      </div>
    </section>
  );
}
