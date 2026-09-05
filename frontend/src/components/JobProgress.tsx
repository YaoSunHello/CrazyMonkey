import type { BackendConnection, JobStatus, StartJobResponse } from "../workspaceTypes";

interface JobProgressProps {
  started: StartJobResponse;
  job?: JobStatus;
  profileLabel: string;
  connection: BackendConnection;
  pollError?: string;
}

export function JobProgress({
  started,
  job,
  profileLabel,
  connection,
  pollError,
}: JobProgressProps) {
  const state = job?.processing_state ?? started.processing_state;
  const events = job?.events ?? [];
  return (
    <div className="progress-page">
      <header className="case-toolbar">
        <div>
          <p className="eyebrow">{started.case_name}</p>
          <h1 tabIndex={-1}>Processing the selected files</h1>
        </div>
        <dl>
          <div><dt>Workflow</dt><dd>{profileLabel}</dd></div>
          <div><dt>Connection</dt><dd>{connection.label}</dd></div>
          <div><dt>Mode</dt><dd><span className="mode-label mode-live">LIVE</span></dd></div>
        </dl>
      </header>

      <div className="progress-grid">
        <section className="progress-documents" aria-labelledby="documents-progress-heading">
          <div className="panel-heading">
            <div>
              <p className="step-label">Upload</p>
              <h2 id="documents-progress-heading">Manifest accepted</h2>
            </div>
            <span className={`processing-badge state-${state.toLowerCase()}`}>{state}</span>
          </div>
          <p className="upload-separation-note">
            File upload is complete. Analysis progress below comes only from backend document states;
            it is not a timer or estimated percentage.
          </p>
          <ul className="document-progress-list">
            {(job?.documents ?? []).map((document) => (
              <li key={document.source_id}>
                <span className={`document-state state-${document.processing_state.toLowerCase()}`} aria-hidden="true" />
                <div>
                  <strong>{document.relative_path}</strong>
                  <small>{document.purpose} · {document.processing_state.replace("_", " ")}</small>
                  {document.error && <p className="inline-error">{document.error}</p>}
                </div>
                {document.computational_outcome && (
                  <span className={`outcome outcome-${document.computational_outcome.toLowerCase()}`}>
                    {document.computational_outcome}
                  </span>
                )}
              </li>
            ))}
            {!job?.documents.length && <li className="pending-row">Waiting for the first backend status snapshot…</li>}
          </ul>
        </section>

        <section className="event-panel" aria-labelledby="events-heading">
          <div className="panel-heading">
            <div>
              <p className="step-label">Operational trace</p>
              <h2 id="events-heading">What the backend is doing</h2>
            </div>
            {job?.event_trace && <span>{job.event_trace.bounded ? `Last ${job.event_trace.max_events} max` : ""}</span>}
          </div>
          {pollError && (
            <div className="warning-banner" role="status">
              <strong>Connection interrupted.</strong> {pollError} Polling will reconnect to this existing job; processing will not restart.
            </div>
          )}
          <ol className="event-list">
            {events.map((event, index) => (
              <li key={typeof event.meta.sequence === "number" ? event.meta.sequence : `${event.at}-${index}`}>
                <time>{formatEventTime(event.at)}</time>
                <span>
                  <strong>{event.label || event.kind}</strong>
                  {event.detail ? ` — ${event.detail}` : event.body ? ` — ${event.body}` : ""}
                  <small className={`trace-status trace-${event.status}`}>{event.status}</small>
                </span>
              </li>
            ))}
            {events.length === 0 && <li className="pending-row">Queued. Waiting for a backend event.</li>}
          </ol>
          {job?.event_trace.truncated && (
            <p className="trace-note">Earlier operational events were discarded by the bounded server trace.</p>
          )}
        </section>
      </div>

      <footer className="progress-footer">
        <code>Job {started.job_id}</code>
        <span>Polling this accepted job until a result is available. No duplicate job will be started.</span>
      </footer>
    </div>
  );
}

function formatEventTime(value: number): string {
  const date = new Date(value * 1_000);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
