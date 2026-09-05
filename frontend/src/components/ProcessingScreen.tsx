import type { ReviewProgress } from "../types";

interface ProcessingScreenProps {
  progress?: ReviewProgress;
  error?: string;
  retrying?: boolean;
  onRetry: () => void;
  onBack: () => void;
}

export function ProcessingScreen({ progress, error, retrying = false, onRetry, onBack }: ProcessingScreenProps) {
  const currentStage = progress?.stages.find((stage) => stage.state === "ACTIVE");
  return (
    <div className="processing-page page-enter">
      <div className="processing-intro">
        <div className="processing-emblem" aria-hidden="true">
          {error ? "!" : <span className="spinner spinner-large" />}
        </div>
        <p className="eyebrow">NAV pack review</p>
        <h1 tabIndex={-1}>{error ? "The review could not continue" : "Reviewing the evidence"}</h1>
        <p className="processing-lede">
          {error
            ? "Your selected files are still available. Retry the review or return to check the pack."
            : currentStage?.label ?? "Waiting for the review service to report progress…"}
        </p>
      </div>

      {error ? (
        <div className="error-panel" role="alert">
          <strong>Review error</strong>
          <p>{error}</p>
          <div className="button-row">
            <button type="button" className="button button-primary" onClick={onRetry} disabled={retrying}>
              {retrying ? <><span className="spinner" aria-hidden="true" />Restarting…</> : "Retry review"}
            </button>
            <button type="button" className="button button-secondary" onClick={onBack} disabled={retrying}>Back to documents</button>
          </div>
        </div>
      ) : (
        <div className="processing-card" aria-busy={progress?.state !== "COMPLETE"}>
          <ol className="stage-list">
            {(progress?.stages ?? []).map((stage) => (
              <li key={stage.code} className={`stage-${stage.state.toLowerCase()}`}>
                <span className="stage-marker" aria-hidden="true">
                  {stage.state === "COMPLETE" ? "✓" : stage.state === "ACTIVE" ? <span className="stage-pulse" /> : ""}
                </span>
                <span>{stage.label}</span>
                <small>{stage.state === "COMPLETE" ? "Complete" : stage.state === "ACTIVE" ? "Current" : "Waiting"}</small>
              </li>
            ))}
          </ol>

          {(progress?.messages.length ?? 0) > 0 && (
            <div className="progress-facts">
              <h2>Review activity</h2>
              <ul>
                {progress?.messages.map((message) => <li key={message.id}>{message.text}</li>)}
              </ul>
            </div>
          )}
          <p className="visually-hidden" role="status" aria-live="polite">
            {currentStage ? `${currentStage.label}, in progress.` : "Review is starting."}
          </p>
        </div>
      )}

      {!error && <button type="button" className="text-button" onClick={onBack}>Back to documents</button>}
    </div>
  );
}
