import { useMemo, useRef, useState } from "react";
import { FinancialMovementChart } from "./FinancialMovementChart";
import type {
  BackendConnection,
  BridgeCapabilities,
  ComputationalOutcome,
  HumanReviewStatus,
  JobResult,
  JobStatus,
  ResultDocument,
  SourceCitation,
  WorkspaceAdapter,
} from "../workspaceTypes";

type ReviewFilter = "ALL" | "FAILED" | "HUMAN";
type ReviewSort = "DOCUMENT" | "STATUS" | "DIFFERENCE";

interface DeskFinding {
  id: string;
  kind: "TRANSACTION_LINK" | "CHECK";
  sourceId: string;
  documentName: string;
  account: string;
  rowLabel: string;
  title: string;
  detail: string;
  evidence: string;
  status: ComputationalOutcome;
  reviewStatus: HumanReviewStatus;
  narrative?: string;
  balance?: string;
  signedMovement?: string;
  derivedBalance?: string;
  comparisonBalance?: string;
  difference?: string;
  currency?: string;
  balanceCitation?: SourceCitation;
  comparisonCitation?: SourceCitation;
}

interface ProfileReviewDeskProps {
  result: JobResult;
  job?: JobStatus;
  profileLabel: string;
  connection: BackendConnection;
  capabilities?: BridgeCapabilities;
  reviewing?: string;
  onReview(findingId: string, status: HumanReviewStatus): void;
  onBack(): void;
  sourceUrl(sourceId: string): string;
  artifactUrl(artifactId: string): string;
  fetchTransactionCsv?: WorkspaceAdapter["fetchTransactionCsv"];
  transactionCsvUrl?: string;
}

export function ProfileReviewDesk({
  result,
  job,
  profileLabel,
  connection,
  capabilities,
  reviewing,
  onReview,
  onBack,
  sourceUrl,
  artifactUrl,
  fetchTransactionCsv,
  transactionCsvUrl,
}: ProfileReviewDeskProps) {
  const evidencePanelRef = useRef<HTMLElement>(null);
  const findings = useMemo(() => flattenFindings(result.documents), [result.documents]);
  const [filter, setFilter] = useState<ReviewFilter>("ALL");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ReviewSort>("DOCUMENT");
  const initialFinding = findings.find((finding) => finding.status !== "PASS") ?? findings[0];
  const [selectedId, setSelectedId] = useState<string | undefined>(initialFinding?.id);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | undefined>(
    initialFinding?.sourceId ?? result.documents[0]?.source_id,
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = findings.filter((finding) => {
      if (filter === "FAILED" && finding.status !== "FAIL") return false;
      if (filter === "HUMAN" && (finding.status === "PASS" || finding.reviewStatus === "REVIEWED")) return false;
      return !needle || [finding.documentName, finding.account, finding.title, finding.detail, finding.narrative]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(needle));
    });
    return [...filtered].sort((left, right) => {
      if (sort === "STATUS") return statusRank(left.status) - statusRank(right.status) || left.documentName.localeCompare(right.documentName);
      if (sort === "DIFFERENCE") return compareDecimalMagnitude(right.difference, left.difference);
      return left.documentName.localeCompare(right.documentName) || left.rowLabel.localeCompare(right.rowLabel, undefined, { numeric: true });
    });
  }, [filter, findings, query, sort]);

  const selected = selectedId ? findings.find((finding) => finding.id === selectedId) : undefined;
  const selectedDocument = result.documents.find((document) => document.source_id === selectedDocumentId)
    ?? result.documents[0];
  const failed = findings.filter((finding) => finding.status === "FAIL").length;
  const unresolved = findings.filter((finding) => finding.status === "UNRESOLVED").length;
  const needsReview = findings.filter((finding) => finding.status !== "PASS" && finding.reviewStatus !== "REVIEWED").length;
  const jsonArtifact = result.artifacts.find((artifact) => artifact.kind === "RESULT_JSON");
  const finalEvents = job?.job_id === result.job_id ? job.events.slice(-100) : [];
  const terminalMessage = result.processing_state === "FAILED"
    ? "Processing failed; no successful verification result is being claimed."
    : result.processing_state === "PARTIAL"
      ? "Deterministic processing completed with document failures."
      : "Deterministic verification complete.";

  return (
    <div className="review-page">
      <header className="case-toolbar review-toolbar">
        <div>
          <button className="back-link" type="button" onClick={onBack}>← New review</button>
          <p className="eyebrow">{result.case_name}</p>
          <h1 tabIndex={-1}>{profileLabel}</h1>
        </div>
        <dl>
          <div><dt>Backend</dt><dd>{connection.label}</dd></div>
          <div><dt>Processing</dt><dd>{result.processing_state}</dd></div>
          <div><dt>Mode</dt><dd><span className="mode-label mode-live">LIVE</span></dd></div>
        </dl>
      </header>

      <div className={`truth-banner ${result.processing_state === "FAILED" ? "truth-banner-failed" : ""}`} role={result.processing_state === "FAILED" ? "alert" : "note"}>
        <strong>{terminalMessage}</strong>
        {result.error && <span>{result.error}</span>}
        <span>{result.agent_resolution.reason}</span>
        <span>Resolution status: <b>{result.agent_resolution.status.replace("_", " ")}</b></span>
      </div>

      {result.exports?.transactions_csv && fetchTransactionCsv && transactionCsvUrl && (
        <FinancialMovementChart
          result={result}
          document={selectedDocument}
          fetchCsv={fetchTransactionCsv}
          downloadUrl={transactionCsvUrl}
          onSelectFinding={(findingId) => {
            const finding = findings.find((item) => item.id === findingId);
            if (!finding) return;
            setSelectedDocumentId(finding.sourceId);
            setSelectedId(findingId);
            setFilter("ALL");
            setQuery("");
            requestAnimationFrame(() => evidencePanelRef.current?.focus());
          }}
        />
      )}

      <div className="review-desk">
        <aside className="document-rail" aria-labelledby="document-rail-heading">
          <div className="rail-heading">
            <div><p className="step-label">Documents</p><h2 id="document-rail-heading">Pack</h2></div>
            <span>{result.documents.length}</span>
          </div>
          <ul>
            {result.documents.map((document) => {
              const documentFindings = findings.filter((finding) => finding.sourceId === document.source_id);
              return (
                <li key={document.source_id} className={selectedDocument?.source_id === document.source_id ? "is-current" : ""}>
                  <button
                    type="button"
                    aria-pressed={selectedDocument?.source_id === document.source_id}
                    onClick={() => {
                      setSelectedDocumentId(document.source_id);
                      setSelectedId(documentFindings.find((finding) => finding.status !== "PASS")?.id ?? documentFindings[0]?.id);
                    }}
                  >
                    <span className={`document-state state-${document.processing_state.toLowerCase()}`} aria-hidden="true" />
                    <span>
                      <strong>{document.statement?.account_short_code || document.filename}</strong>
                      <small title={document.relative_path}>{document.relative_path}</small>
                    </span>
                    {document.computational_outcome && (
                      <span className={`outcome outcome-${document.computational_outcome.toLowerCase()}`}>{document.computational_outcome}</span>
                    )}
                  </button>
                  {document.error && <p className="inline-error">{document.error}</p>}
                </li>
              );
            })}
          </ul>

          <div className="rail-summary">
            <div><span>Failed checks</span><strong className={failed ? "text-fail" : ""}>{failed}</strong></div>
            <div><span>Unresolved</span><strong className={unresolved ? "text-warning" : ""}>{unresolved}</strong></div>
            <div><span>Needs review</span><strong>{needsReview}</strong></div>
          </div>
        </aside>

        <section className="check-workspace" aria-labelledby="check-table-heading">
          <div className="check-toolbar">
            <div>
              <p className="step-label">Transactions and checks</p>
              <h2 id="check-table-heading">Show the arithmetic</h2>
            </div>
            <div className="filter-tabs" role="group" aria-label="Filter checks">
              <button type="button" aria-pressed={filter === "ALL"} className={filter === "ALL" ? "is-active" : ""} onClick={() => setFilter("ALL")}>All</button>
              <button type="button" aria-pressed={filter === "FAILED"} className={filter === "FAILED" ? "is-active" : ""} onClick={() => setFilter("FAILED")}>Failed checks</button>
              <button type="button" aria-pressed={filter === "HUMAN"} className={filter === "HUMAN" ? "is-active" : ""} onClick={() => setFilter("HUMAN")}>Needs human review</button>
            </div>
          </div>

          <div className="search-sort-row">
            <label>
              <span className="visually-hidden">Search transactions and checks</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search account, source or narrative" />
            </label>
            <label>
              <span>Sort</span>
              <select value={sort} onChange={(event) => setSort(event.target.value as ReviewSort)}>
                <option value="DOCUMENT">Document order</option>
                <option value="STATUS">Outcome</option>
                <option value="DIFFERENCE">Difference</option>
              </select>
            </label>
          </div>

          <div className="check-table-scroll">
            <table className="check-table">
              <thead>
                <tr>
                  <th scope="col">Source / check</th>
                  <th scope="col" className="numeric">Balance</th>
                  <th scope="col" className="numeric">Signed movement</th>
                  <th scope="col" className="numeric">Derived</th>
                  <th scope="col" className="numeric">Comparison</th>
                  <th scope="col" className="numeric">Difference</th>
                  <th scope="col">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((finding) => (
                  <tr
                    key={finding.id}
                    className={`${selected?.id === finding.id ? "is-selected" : ""} row-${finding.status.toLowerCase()}`}
                    onClick={() => {
                      setSelectedDocumentId(finding.sourceId);
                      setSelectedId(finding.id);
                    }}
                  >
                    <th scope="row">
                      <button type="button" onClick={() => {
                        setSelectedDocumentId(finding.sourceId);
                        setSelectedId(finding.id);
                      }}>
                        <strong>{finding.account} · {finding.rowLabel}</strong>
                        <small>{finding.narrative || finding.title}</small>
                      </button>
                    </th>
                    <td className="numeric">{displayDecimal(finding.balance)}</td>
                    <td className="numeric">{displayDecimal(finding.signedMovement)}</td>
                    <td className="numeric">{displayDecimal(finding.derivedBalance)}</td>
                    <td className="numeric">{displayDecimal(finding.comparisonBalance)}</td>
                    <td className="numeric difference-cell">{displayDecimal(finding.difference)}</td>
                    <td>
                      <span className={`outcome outcome-${finding.status.toLowerCase()}`}>{finding.status}</span>
                      {finding.reviewStatus !== "UNREVIEWED" && <small className="review-marker">{finding.reviewStatus.replaceAll("_", " ")}</small>}
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && <tr><td colSpan={7} className="empty-row">No checks match this view.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <aside
          ref={evidencePanelRef}
          tabIndex={-1}
          className={`evidence-panel ${selected || selectedDocument ? "is-open" : ""}`}
          aria-labelledby={selected || selectedDocument ? "evidence-heading" : undefined}
          aria-label={!selected && !selectedDocument ? "Evidence details" : undefined}
        >
          {selectedDocument && (
            <section className="source-document-details" aria-label="Original document">
              <a className="button button-secondary" href={sourceUrl(selectedDocument.source_id)} target="_blank" rel="noreferrer">
                {selectedDocument.purpose === "SOURCE" ? "Open original PDF" : "Open original workbook"}
              </a>
              <dl className="finding-meta">
                <div><dt>Account</dt><dd>{selectedDocument.statement?.account_number || selectedDocument.statement?.account_short_code || "—"}</dd></div>
                <div><dt>Currency</dt><dd>{selectedDocument.statement?.currency || "—"}</dd></div>
                <div><dt>Parsed rows</dt><dd>{selectedDocument.statement?.row_count ?? selectedDocument.rows.length}</dd></div>
                <div><dt>Closing balance</dt><dd>{displayDecimal(selectedDocument.statement?.closing_balance ?? undefined)}</dd></div>
                {selectedDocument.sha256 && <div><dt>Source SHA-256</dt><dd title={selectedDocument.sha256}>{abbreviateIdentity(selectedDocument.sha256)}</dd></div>}
                {selectedDocument.atlas?.document_id && <div><dt>ATLAS document</dt><dd title={selectedDocument.atlas.document_id}>{abbreviateIdentity(selectedDocument.atlas.document_id)}</dd></div>}
              </dl>
            </section>
          )}
          {selected ? (
            <>
              <div className="panel-heading">
                <div><p className="step-label">Selected finding</p><h2 id="evidence-heading">{selected.title}</h2></div>
                <span className={`outcome outcome-${selected.status.toLowerCase()}`}>{selected.status}</span>
              </div>
              <dl className="finding-meta">
                <div><dt>Source</dt><dd>{selected.documentName}</dd></div>
                <div><dt>Account</dt><dd>{selected.account}</dd></div>
                <div><dt>Check outcome</dt><dd>{selected.status}</dd></div>
                <div><dt>Human review</dt><dd>{selected.reviewStatus.replaceAll("_", " ")}</dd></div>
              </dl>

              {selected.kind === "TRANSACTION_LINK" && (
                <section className="calculation-card" aria-labelledby="calculation-heading">
                  <h3 id="calculation-heading">Backend-supplied calculation</h3>
                  <div className="equation-line"><span>Balance</span><strong>{displayDecimal(selected.balance)} {selected.currency}</strong></div>
                  <div className="equation-line"><span>− signed movement</span><strong>{displayDecimal(selected.signedMovement)} {selected.currency}</strong></div>
                  <div className="equation-line equation-result"><span>= derived balance</span><strong>{displayDecimal(selected.derivedBalance)} {selected.currency}</strong></div>
                  <div className="equation-line"><span>Comparison balance</span><strong>{displayDecimal(selected.comparisonBalance)} {selected.currency}</strong></div>
                  <div className="equation-line equation-difference"><span>Difference</span><strong>{displayDecimal(selected.difference)} {selected.currency}</strong></div>
                  <p>Displayed as exact decimal strings returned by the verifier. The browser does not recalculate the outcome.</p>
                </section>
              )}

              <section className="evidence-copy">
                <h3>Why this result</h3>
                <p>{selected.detail}</p>
                {selected.evidence && <pre>{selected.evidence}</pre>}
              </section>

              <section className="source-action">
                <h3>Source evidence</h3>
                {selected.balanceCitation || selected.comparisonCitation ? (
                  <div className="citation-list">
                    {([
                      ["Balance row", selected.balanceCitation],
                      ["Comparison row", selected.comparisonCitation],
                    ] as const).map(([label, citation]) => citation && (
                      <div key={label}>
                        <strong>{label}</strong>
                        <p>
                          Page {citation.page} · bounding box ({round(citation.bbox.x0)}, {round(citation.bbox.top)})–({round(citation.bbox.x1)}, {round(citation.bbox.bottom)})
                        </p>
                        <button className="button button-secondary" type="button" onClick={() => openSource(sourceUrl(selected.sourceId), citation.page)}>
                          Open {label.toLowerCase()} source page
                        </button>
                      </div>
                    ))}
                    <small>The native PDF viewer opens each verified page. No highlight is drawn unless the viewer can honour the real coordinates.</small>
                  </div>
                ) : (
                  <p>No structured page citation was supplied for this check.</p>
                )}
              </section>

              {selected.status !== "PASS" && (
                <section className="review-actions" aria-labelledby="next-action-heading">
                  <h3 id="next-action-heading">Next action</h3>
                  <p>Recording a human decision never changes {selected.status} into PASS.</p>
                  <div>
                    <button
                      className="button button-primary"
                      type="button"
                      disabled={reviewing === selected.id || selected.reviewStatus === "REVIEWED"}
                      onClick={() => onReview(selected.id, "REVIEWED")}
                    >
                      {reviewing === selected.id ? "Saving…" : "Mark reviewed"}
                    </button>
                    <button
                      className="button button-secondary"
                      type="button"
                      disabled={reviewing === selected.id}
                      onClick={() => onReview(selected.id, "NEEDS_FOLLOW_UP")}
                    >
                      Needs follow-up
                    </button>
                  </div>
                </section>
              )}
            </>
          ) : selectedDocument ? (
            <>
              <div className="panel-heading">
                <div>
                  <p className="step-label">Selected document</p>
                  <h2 id="evidence-heading">{selectedDocument.statement?.account_short_code || selectedDocument.filename}</h2>
                </div>
                <span className={`processing-badge state-${selectedDocument.processing_state.toLowerCase()}`}>
                  {selectedDocument.processing_state}
                </span>
              </div>
              <dl className="finding-meta">
                <div><dt>Source</dt><dd>{selectedDocument.relative_path}</dd></div>
                <div><dt>Processing</dt><dd>{selectedDocument.processing_state}</dd></div>
                <div><dt>Check outcome</dt><dd>{selectedDocument.computational_outcome ?? "NOT AVAILABLE"}</dd></div>
              </dl>
              <section className="evidence-copy">
                <h3>{selectedDocument.error ? "Document processing failed" : "No checks returned"}</h3>
                {selectedDocument.error
                  ? <p className="inline-error" role="alert">{selectedDocument.error}</p>
                  : <p>This document has no transaction or document checks to inspect.</p>}
                <p>Select another document or check to inspect its arithmetic and source evidence.</p>
              </section>
            </>
          ) : <p>Select a transaction or check to inspect its arithmetic and evidence.</p>}
        </aside>
      </div>

      <section className="output-dock" aria-labelledby="outputs-heading">
        <div>
          <p className="step-label">Artifacts</p>
          <h2 id="outputs-heading">Available outputs</h2>
          <p>Only files actually generated by this backend job can be downloaded.</p>
        </div>
        <div className="output-actions">
          {jsonArtifact ? (
            <a className="button button-primary" href={artifactUrl(jsonArtifact.artifact_id)} download={jsonArtifact.filename}>Download JSON result</a>
          ) : <button className="button button-primary" type="button" disabled>JSON unavailable</button>}
          <button className="button button-secondary" type="button" disabled title={capabilities?.artifacts.workbook.reason}>Download review workbook</button>
          <button className="button button-secondary" type="button" disabled title={capabilities?.artifacts.report.reason}>Download report</button>
        </div>
        <div className="unavailable-reasons">
          {!capabilities?.artifacts.workbook.available && <p><strong>Workbook:</strong> {capabilities?.artifacts.workbook.reason ?? "Not advertised by the backend."}</p>}
          {!capabilities?.artifacts.report.available && <p><strong>Report:</strong> {capabilities?.artifacts.report.reason ?? "Not advertised by the backend."}</p>}
        </div>
      </section>

      {finalEvents.length > 0 && (
        <details className="technical-details completed-trace">
          <summary>Processing history ({finalEvents.length} events)</summary>
          <ol className="event-list" aria-label="Actual processing history">
            {finalEvents.map((event, index) => (
              <li key={typeof event.meta.sequence === "number" ? event.meta.sequence : `${event.at}-${index}`}>
                <time dateTime={new Date(event.at * 1_000).toISOString()}>{new Date(event.at * 1_000).toLocaleTimeString()}</time>
                <span><strong>{event.label || event.kind}</strong>{event.detail ? ` — ${event.detail}` : event.body ? ` — ${event.body}` : ""}</span>
              </li>
            ))}
          </ol>
          {(job?.event_trace.truncated || (job?.events.length ?? 0) > finalEvents.length) && <p>Showing the latest retained backend events.</p>}
        </details>
      )}

      <details className="technical-details">
        <summary>Technical details</summary>
        <dl>
          <div><dt>Job</dt><dd><code>{result.job_id}</code></dd></div>
          <div><dt>Execution</dt><dd>{result.execution_label}</dd></div>
          <div><dt>Reference validation</dt><dd>{result.reference_validation.status.replace("_", " ")}</dd></div>
          <div><dt>Profile projection</dt><dd>{result.profile_projection.status}</dd></div>
        </dl>
        {result.reference_validation.error && <p>{result.reference_validation.error}</p>}
        {result.error && <p>{result.error}</p>}
        {result.profile_projection.reason && <p>{result.profile_projection.reason}</p>}
      </details>
    </div>
  );
}

function flattenFindings(documents: ResultDocument[]): DeskFinding[] {
  const out: DeskFinding[] = [];
  for (const document of documents) {
    const rows = new Map(document.rows.map((row) => [row.row_id, row]));
    for (const link of document.transaction_links) {
      const row = rows.get(link.newer_row_id);
      out.push({
        id: link.finding_id,
        kind: "TRANSACTION_LINK",
        sourceId: document.source_id,
        documentName: document.filename,
        account: document.statement?.account_short_code || document.filename,
        rowLabel: `link ${link.link_id}`,
        title: "Running-balance link",
        detail: `${link.balance} − (${link.signed_movement}) = ${link.derived_balance}; comparison ${link.comparison_balance}; difference ${link.difference}.`,
        evidence: "",
        status: link.status,
        reviewStatus: link.review_status,
        narrative: row?.narrative || row?.bank_reference,
        balance: link.balance ?? undefined,
        signedMovement: link.signed_movement ?? undefined,
        derivedBalance: link.derived_balance ?? undefined,
        comparisonBalance: link.comparison_balance ?? undefined,
        difference: link.difference ?? undefined,
        currency: document.statement?.currency,
        balanceCitation: link.citations.balance,
        comparisonCitation: link.citations.comparison_balance,
      });
    }
    for (const check of document.checks) {
      out.push({
        id: check.finding_id,
        kind: "CHECK",
        sourceId: document.source_id,
        documentName: document.filename,
        account: document.statement?.account_short_code || document.filename,
        rowLabel: check.name,
        title: check.name.replaceAll("_", " "),
        detail: check.detail,
        evidence: check.evidence,
        status: check.status,
        reviewStatus: check.review_status,
      });
    }
  }
  return out;
}

function displayDecimal(value?: string): string {
  if (value === undefined || value === null || value === "") return "—";
  const [integer, fraction] = value.split(".");
  const sign = integer.startsWith("-") ? "−" : "";
  const digits = integer.replace(/^-/, "");
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}${grouped}${fraction === undefined ? "" : `.${fraction}`}`;
}

function abbreviateIdentity(value: string): string {
  return value.length > 24 ? `${value.slice(0, 16)}…${value.slice(-8)}` : value;
}

function statusRank(status: ComputationalOutcome): number {
  return status === "FAIL" ? 0 : status === "UNRESOLVED" ? 1 : 2;
}

function compareDecimalMagnitude(left?: string, right?: string): number {
  const parts = (value?: string) => {
    const [rawInteger = "0", rawFraction = ""] = (value ?? "0").replace(/^-/, "").split(".");
    return { integer: rawInteger.replace(/^0+(?=\d)/, ""), fraction: rawFraction };
  };
  const a = parts(left);
  const b = parts(right);
  if (a.integer.length !== b.integer.length) return a.integer.length - b.integer.length;
  const integerOrder = a.integer.localeCompare(b.integer);
  if (integerOrder) return integerOrder;
  const fractionLength = Math.max(a.fraction.length, b.fraction.length);
  return a.fraction.padEnd(fractionLength, "0").localeCompare(b.fraction.padEnd(fractionLength, "0"));
}

function round(value: number): string {
  return value.toFixed(0);
}

function openSource(url: string, page?: number): void {
  const target = page ? `${url}#page=${page}` : url;
  window.open(target, "_blank", "noopener,noreferrer");
}
