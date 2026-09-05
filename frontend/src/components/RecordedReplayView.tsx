import { useMemo, useState } from "react";
import type { BackendConnection, RecordedReplay } from "../workspaceTypes";

interface ReplayRow {
  id: string;
  source: string;
  page: string;
  date: string;
  narrative: string;
  amount: string;
  counterparty: string;
  project: string;
  classification: string;
}

interface RecordedReplayViewProps {
  replay: RecordedReplay;
  profileLabel: string;
  connection: BackendConnection;
  onBack(): void;
}

export function RecordedReplayView({ replay, profileLabel, connection, onBack }: RecordedReplayViewProps) {
  const [selectedRunId, setSelectedRunId] = useState(replay.accounts[0]?.run_id ?? "");
  const account = replay.accounts.find((item) => item.run_id === selectedRunId) ?? replay.accounts[0];
  const rows = useMemo(() => replayRows(account?.envelope), [account]);

  return (
    <div className="replay-page">
      <header className="case-toolbar review-toolbar">
        <div>
          <button className="back-link" type="button" onClick={onBack}>← Back to new review</button>
          <p className="eyebrow">Recorded batch {replay.original_batch_id}</p>
          <h1 tabIndex={-1}>{profileLabel || replay.profile_id}</h1>
        </div>
        <dl>
          <div><dt>Backend</dt><dd>{connection.label}</dd></div>
          <div><dt>Recorded duration</dt><dd>{formatDuration(replay.recorded_seconds)}</dd></div>
          <div><dt>Mode</dt><dd><span className="mode-label mode-replay">RECORDED REPLAY</span></dd></div>
        </dl>
      </header>

      <div className="replay-truth-banner" role="note">
        <strong>This is playback, not a rerun.</strong>
        <span>{replay.note}</span>
        <span>Model calls: {replay.model_calls}. Event trace available: no. Idle-time compression performed: no.</span>
      </div>

      <div className="replay-grid">
        <aside className="document-rail" aria-labelledby="replay-documents-heading">
          <div className="rail-heading">
            <div><p className="step-label">Original runs</p><h2 id="replay-documents-heading">Accounts</h2></div>
            <span>{replay.accounts.length}</span>
          </div>
          <ul>
            {replay.accounts.map((item) => (
              <li key={item.run_id} className={selectedRunId === item.run_id ? "is-current" : ""}>
                <button type="button" onClick={() => setSelectedRunId(item.run_id)}>
                  <span className={`document-state ${item.accepted ? "state-succeeded" : "state-failed"}`} aria-hidden="true" />
                  <span><strong>{item.account}</strong><small>{item.run_id}</small></span>
                  <span className={`outcome ${item.accepted ? "outcome-pass" : "outcome-fail"}`}>{item.accepted ? "ACCEPTED" : "REJECTED"}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="replay-table-panel" aria-labelledby="replay-table-heading">
          <div className="panel-heading">
            <div>
              <p className="step-label">Committed result envelope</p>
              <h2 id="replay-table-heading">{account?.account ?? "Recorded account"}</h2>
            </div>
            {account && <span>{account.attempts} attempts · {formatDuration(account.seconds)}</span>}
          </div>
          <div className="check-table-scroll">
            <table className="replay-table">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Date</th>
                  <th scope="col">Narrative</th>
                  <th scope="col" className="numeric">Amount</th>
                  <th scope="col">Counterparty</th>
                  <th scope="col">Project</th>
                  <th scope="col">Classification</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.source}</strong><small>Page {row.page}</small></td>
                    <td>{row.date}</td>
                    <td className="narrative-cell">{row.narrative}</td>
                    <td className="numeric">{row.amount}</td>
                    <td>{row.counterparty}</td>
                    <td>{row.project}</td>
                    <td>{row.classification}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={7} className="empty-row">This recorded envelope has no row array the review table can display.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="evidence-panel replay-evidence" aria-labelledby="replay-evidence-heading">
          <p className="step-label">Playback limits</p>
          <h2 id="replay-evidence-heading">Evidence is read-only</h2>
          <p>
            The committed example contains source filenames, page references, result envelopes and recorded durations.
            It does not contain the original-file retrieval route or a trace stream.
          </p>
          <dl className="finding-meta">
            <div><dt>Original batch</dt><dd>{replay.original_batch_id}</dd></div>
            <div><dt>Profile ID</dt><dd>{replay.profile_id}</dd></div>
            <div><dt>Original run</dt><dd>{account?.run_id ?? "—"}</dd></div>
            <div><dt>Accepted</dt><dd>{account ? String(account.accepted) : "—"}</dd></div>
            <div><dt>Compressed idle time</dt><dd>No</dd></div>
          </dl>
          <button className="button button-secondary" type="button" disabled>Original source unavailable in replay</button>
          <small>No source file, check result or export was regenerated by opening this screen.</small>
        </aside>
      </div>
    </div>
  );
}

function replayRows(envelope: Record<string, unknown> | undefined): ReplayRow[] {
  if (!envelope) return [];
  const candidate = Array.isArray(envelope.statement_rows)
    ? envelope.statement_rows
    : Array.isArray(envelope.extracted_rows)
      ? envelope.extracted_rows
      : [];
  return candidate.filter(isRecord).map((row, index) => ({
    id: String(row.row_id ?? `${row.source_file ?? row.source_document ?? "row"}-${index}`),
    source: stringValue(row.source_file ?? row.source_document),
    page: stringValue(row.source_page),
    date: stringValue(row.transaction_date ?? row.value_date),
    narrative: stringValue(row.raw_narrative ?? row.source_snippet),
    amount: decimalText(row.amount),
    counterparty: resolutionText(row.counterparty_match ?? row.counterparty_status),
    project: resolutionText(row.project_code_match ?? row.project_code_status),
    classification: stringValue(row.classification),
  }));
}

function resolutionText(value: unknown): string {
  if (typeof value === "string") return value;
  if (isRecord(value)) {
    const status = stringValue(value.status);
    const matched = stringValue(value.matched_name);
    return matched ? `${status}: ${matched}` : status;
  }
  return "—";
}

function decimalText(value: unknown): string {
  if (typeof value !== "number" && typeof value !== "string") return "—";
  const raw = String(value);
  const [integer, fraction] = raw.split(".");
  const sign = integer.startsWith("-") ? "−" : "";
  const digits = integer.replace(/^-/, "");
  return `${sign}${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction ? `.${fraction}` : ""}`;
}

function stringValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}
