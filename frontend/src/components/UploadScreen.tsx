import { useId, useRef, useState } from "react";
import type { DetectedUpload, DocumentRole } from "../types";
import { documentRoleLabels } from "../utils/format";

const roleOptions = Object.entries(documentRoleLabels) as [DocumentRole, string][];

interface UploadScreenProps {
  documents: DetectedUpload[];
  adapterMode: "mock" | "live";
  busy: boolean;
  canStart: boolean;
  startHelp: string;
  onSelectFiles: (files: File[]) => Promise<void>;
  onChangeRole: (documentId: string, role: DocumentRole) => void;
  onRemoveDocument: (documentId: string) => void;
  onStart: () => void;
  onLoadDemo: () => void;
}

export function UploadScreen({
  documents,
  adapterMode,
  busy,
  canStart,
  startHelp,
  onSelectFiles,
  onChangeRole,
  onRemoveDocument,
  onStart,
  onLoadDemo,
}: UploadScreenProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  async function selectFiles(files: FileList | null) {
    if (!files?.length) return;
    await onSelectFiles(Array.from(files));
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="upload-page page-enter">
      <section className="hero-copy" aria-labelledby="upload-heading">
        <p className="eyebrow">Independent NAV review</p>
        <h1 id="upload-heading" tabIndex={-1}>Review your NAV pack before you sign it.</h1>
        <p className="hero-lede">
          Upload the administrator workbook and supporting fund documents. CrazyMonkey checks investor
          terms, calculations and evidence, then surfaces anything requiring review.
        </p>

        <ol className="workflow-preview" aria-label="How CrazyMonkey works">
          <li><span aria-hidden="true">1</span><div><strong>Provide the pack</strong><small>Workbook, LPA, side letters and register</small></div></li>
          <li><span aria-hidden="true">2</span><div><strong>Run an independent check</strong><small>Terms, evidence and calculations compared</small></div></li>
          <li><span aria-hidden="true">3</span><div><strong>Investigate exceptions</strong><small>Every finding linked back to its source</small></div></li>
        </ol>

        <div className="demo-callout">
          <div>
            <strong>Want to see the review first?</strong>
            <p>
              {adapterMode === "mock"
                ? "Uses a clearly labelled development fixture while Atlas is not connected."
                : "Runs the Atlas synthetic fund workflow."}
            </p>
          </div>
          <button className="button button-secondary" type="button" onClick={onLoadDemo} disabled={busy} aria-busy={busy}>
            {busy ? <><span className="spinner" aria-hidden="true" />Loading demo…</> : "Load synthetic demo"}
          </button>
        </div>
      </section>

      <section className="upload-card" aria-labelledby="nav-pack-heading">
        <div className="section-heading compact">
          <div>
            <p className="step-label">New review</p>
            <h2 id="nav-pack-heading">Add your NAV pack</h2>
          </div>
          <span className="security-label">
            <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 2.8 16 5v4.2c0 4-2.5 6.5-6 8-3.5-1.5-6-4-6-8V5l6-2.2Z" /></svg>
            Review workspace
          </span>
        </div>

        <div
          className={`upload-dropzone ${dragActive ? "is-dragging" : ""}`}
          onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => { if (event.currentTarget === event.target) setDragActive(false); }}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            void selectFiles(event.dataTransfer.files);
          }}
        >
          <div className="upload-symbol" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5v4A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-4" /></svg>
          </div>
          <strong>Drop the full pack here</strong>
          <p>XLSX, CSV and text PDF · up to 25 MB per file</p>
          <input
            ref={inputRef}
            className="visually-hidden"
            id={inputId}
            type="file"
            multiple
            accept=".xlsx,.csv,.pdf"
            onChange={(event) => void selectFiles(event.target.files)}
          />
          <label className="button button-secondary button-small" htmlFor={inputId}>Select files</label>
        </div>

        <div className="role-key" aria-label="Documents to include">
          <span><i aria-hidden="true">X</i>NAV workbook</span>
          <span><i aria-hidden="true">P</i>LPA</span>
          <span><i aria-hidden="true">P</i>Side letters</span>
          <span><i aria-hidden="true">D</i>Investor register</span>
        </div>

        {documents.length > 0 && (
          <div className="detected-documents">
            <div className="detected-header">
              <h3>Detected documents</h3>
              <span>{documents.length} {documents.length === 1 ? "file" : "files"}</span>
            </div>
            <ul className="document-list">
              {documents.map((document) => (
                <li key={document.id} className={document.recognition === "NEEDS_CONFIRMATION" ? "needs-confirmation" : ""}>
                  <div className="document-mark" aria-hidden="true">{document.filename.toLowerCase().endsWith(".pdf") ? "P" : "X"}</div>
                  <div className="document-info">
                    <strong>{document.filename}</strong>
                    {document.recognition === "RECOGNISED" ? (
                      <span className="recognised"><span aria-hidden="true">✓</span> Recognised as {documentRoleLabels[document.role]}</span>
                    ) : (
                      <span className="needs-label"><span aria-hidden="true">!</span> Confirm this document’s role</span>
                    )}
                  </div>
                  {document.recognition === "NEEDS_CONFIRMATION" && (
                    <div className="role-select-wrap">
                      <label htmlFor={`role-${document.id}`}>Document role</label>
                      <select
                        id={`role-${document.id}`}
                        value={document.role}
                        onChange={(event) => onChangeRole(document.id, event.target.value as DocumentRole)}
                      >
                        {roleOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </div>
                  )}
                  <button className="icon-button subtle" type="button" aria-label={`Remove ${document.filename}`} onClick={() => onRemoveDocument(document.id)}>
                    <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15" /></svg>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="upload-actions">
          <div>
            <p className="action-help" id="start-review-help">{startHelp}</p>
          </div>
          <button
            className="button button-primary"
            type="button"
            onClick={onStart}
            disabled={!canStart || busy}
            aria-describedby="start-review-help"
          >
            {busy ? <><span className="spinner" aria-hidden="true" />Starting review…</> : <>Start review <span aria-hidden="true">→</span></>}
          </button>
        </div>
      </section>
    </div>
  );
}
