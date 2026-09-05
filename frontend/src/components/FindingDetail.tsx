import { useMemo, useRef, useState } from "react";
import type {
  EvidenceReference,
  HumanReviewState,
  HumanReviewUpdate,
  ReviewFinding,
  TermCorrection,
} from "../types";
import { documentRoleLabels, formatDateTime, formatMoney } from "../utils/format";
import { CorrectionDialog } from "./CorrectionDialog";
import { FindingStatusBadge, HumanReviewBadge } from "./StatusBadge";

interface FindingDetailProps {
  finding: ReviewFinding;
  saving: boolean;
  onBack: () => void;
  onOpenEvidence: (evidence: EvidenceReference) => void;
  onHumanReview: (update: HumanReviewUpdate) => Promise<void>;
  onCorrectTerm: (correction: TermCorrection) => Promise<void>;
  onUploadDocument: (file: File) => Promise<void>;
  canUploadDocument: boolean;
  canCorrectTerm: boolean;
}

export function FindingDetail({
  finding,
  saving,
  onBack,
  onOpenEvidence,
  onHumanReview,
  onCorrectTerm,
  onUploadDocument,
  canUploadDocument,
  canCorrectTerm,
}: FindingDetailProps) {
  const [reviewerName, setReviewerName] = useState("");
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState<string>();
  const [localError, setLocalError] = useState<string>();
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const missingFileRef = useRef<HTMLInputElement>(null);

  const difference = useMemo(() => {
    if (!finding.difference || !finding.administratorValue || !finding.expectedValue) return "—";
    if (finding.difference.amount === 0) return formatMoney(finding.difference);
    return `${formatMoney(finding.difference)} ${
      finding.administratorValue.amount > finding.expectedValue.amount ? "over expected" : "under expected"
    }`;
  }, [finding]);

  async function applyReviewState(state: HumanReviewState, requiresNote = false) {
    if (!reviewerName.trim()) {
      setLocalError("Enter a reviewer display name before recording a review action.");
      return;
    }
    if (requiresNote && !note.trim()) {
      setLocalError("Add a note explaining the follow-up or review action.");
      return;
    }
    setLocalError(undefined);
    try {
      await onHumanReview({ state, note: note.trim() || undefined, reviewerName: reviewerName.trim() });
      setFeedback(
        state === "REVIEWED"
          ? `Marked reviewed. The computational finding remains ${finding.status.toLowerCase().replace("_", " ")}.`
          : "Human review state saved.",
      );
      setNote("");
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "The review action could not be saved. Check the notification for details.");
    }
  }

  async function addNote() {
    if (!reviewerName.trim()) {
      setLocalError("Enter a reviewer display name before adding a note.");
      return;
    }
    if (!note.trim()) {
      setLocalError("Write a note before saving it.");
      return;
    }
    setLocalError(undefined);
    try {
      await onHumanReview({
        state: finding.humanReviewState,
        note: note.trim(),
        reviewerName: reviewerName.trim(),
      });
      setFeedback("Note added to the audit trail.");
      setNote("");
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "The note could not be saved. Check the notification for details.");
    }
  }

  async function submitCorrection(correction: TermCorrection) {
    await onCorrectTerm(correction);
    setCorrectionOpen(false);
    setFeedback("Correction recorded and a new review version created.");
  }

  return (
    <div className="detail-page page-enter">
      <button className="back-button" type="button" onClick={onBack}><span aria-hidden="true">←</span> Back to findings</button>

      <header className="detail-header">
        <div>
          <p className="eyebrow">Finding detail</p>
          <h1 tabIndex={-1}>{finding.investorId} <span>{finding.checkName}</span></h1>
        </div>
        <div className="dual-status">
          <div><small>Finding</small><FindingStatusBadge status={finding.status} /></div>
          <div><small>Human review</small><HumanReviewBadge state={finding.humanReviewState} /></div>
        </div>
      </header>

      <section className={`finding-hero finding-hero-${finding.status.toLowerCase().replace("_", "-")}`} aria-labelledby="comparison-heading">
        <div className="finding-hero-heading">
          <div>
            <p className="eyebrow">Value comparison</p>
            <h2 id="comparison-heading">{finding.status === "CANNOT_VERIFY" ? "Evidence is incomplete" : "Management fee comparison"}</h2>
          </div>
          <FindingStatusBadge status={finding.status} />
        </div>

        <dl className="value-comparison">
          <div><dt>Administrator</dt><dd>{formatMoney(finding.administratorValue)}</dd><small>reported value</small></div>
          <div><dt>Expected</dt><dd>{formatMoney(finding.expectedValue)}</dd><small>{finding.expectedValue ? "recalculated value" : "not established"}</small></div>
          <div className="difference-value"><dt>Difference</dt><dd>{difference}</dd><small>{finding.difference ? "absolute variance" : "cannot calculate"}</small></div>
        </dl>

        <div className="plain-explanation">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 2.5a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 6v5m0-7v.1" /></svg>
          <p>{finding.explanation}</p>
        </div>

        {finding.requiredAction && (
          <div className="required-action">
            <div><strong>Required action</strong><p>{finding.requiredAction.label}</p></div>
            {canUploadDocument ? (
              <>
                <input
                  ref={missingFileRef}
                  className="visually-hidden"
                  id="missing-support-file"
                  type="file"
                  accept=".pdf,.xlsx,.csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void onUploadDocument(file);
                    if (missingFileRef.current) missingFileRef.current.value = "";
                  }}
                />
                <label className="button button-secondary" htmlFor="missing-support-file">Upload document</label>
              </>
            ) : (
              <div>
                <button className="button button-secondary" type="button" disabled>Upload document</button>
                <p className="action-help">Available when Atlas is connected.</p>
              </div>
            )}
          </div>
        )}
      </section>

      <div className="detail-grid">
        <div className="detail-main">
          {finding.calculation && (
            <section className="detail-section calculation-section" aria-labelledby="calculation-heading">
              <div className="section-title-row">
                <div><p className="eyebrow">Deterministic check</p><h2 id="calculation-heading">Calculation</h2></div>
                <span className="recomputed-label"><span aria-hidden="true">↻</span> Recomputed</span>
              </div>
              <dl className="calculation-inputs">
                {finding.calculation.inputs.map((input) => <div key={input.label}><dt>{input.label}</dt><dd>{input.value}</dd></div>)}
              </dl>
              <div className="formula-block">
                <code>{finding.calculation.expression}</code>
                <span aria-hidden="true">=</span>
                <strong>{formatMoney(finding.calculation.result)}</strong>
              </div>
            </section>
          )}

          <section className="detail-section" aria-labelledby="evidence-heading">
            <div className="section-title-row">
              <div><p className="eyebrow">Traceable inputs</p><h2 id="evidence-heading">Source evidence</h2></div>
              <span className="source-count">{finding.evidence.length} sources</span>
            </div>
            {finding.evidence.length > 0 ? (
              <ul className="evidence-list">
                {finding.evidence.map((evidence) => (
                  <li key={evidence.id}>
                    <div className={`evidence-type type-${evidence.sourceKind.toLowerCase()}`} aria-hidden="true">
                      {evidence.sourceKind === "SPREADSHEET" ? "X" : evidence.sourceKind === "CSV" ? "C" : evidence.sourceKind === "TEXT" ? "T" : "P"}
                    </div>
                    <div>
                      <strong>{documentRoleLabels[evidence.documentRole]}</strong>
                      <span>{evidence.filename}</span>
                      <small>{evidence.locator}</small>
                    </div>
                    <button
                      className="evidence-open"
                      type="button"
                      onClick={() => onOpenEvidence(evidence)}
                      aria-label={`Open ${evidence.filename} evidence, ${evidence.locator}`}
                    >
                      Open source <span aria-hidden="true">↗</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-inline">No source references were returned for this finding.</p>
            )}
          </section>

          <section className="detail-section" aria-labelledby="audit-trail-heading">
            <div className="section-title-row"><div><p className="eyebrow">Observable audit trail</p><h2 id="audit-trail-heading">Checks performed</h2></div></div>
            <ul className="checks-list">
              {finding.checksPerformed.map((check) => (
                <li key={check.id} className={`check-${check.state.toLowerCase()}`}>
                  <span aria-hidden="true">{check.state === "COMPLETE" ? "✓" : check.state === "CONCERN" ? "!" : "?"}</span>
                  {check.label}
                  <small>{check.state === "COMPLETE" ? "Completed" : check.state === "CONCERN" ? "Concern" : "Unresolved"}</small>
                </li>
              ))}
            </ul>

            <div className="agent-observations">
              {finding.challengerConcern && (
                <article className="observation concern-observation">
                  <span aria-hidden="true">!</span><div><h3>Challenge result</h3><p>{finding.challengerConcern}</p></div>
                </article>
              )}
              {finding.verifierStatement && (
                <article className="observation verifier-observation">
                  <span aria-hidden="true">✓</span><div><h3>Verification result</h3><p>{finding.verifierStatement}</p></div>
                </article>
              )}
            </div>
            <p className="reasoning-note">This shows observable review actions and conclusions, not private chain-of-thought.</p>
          </section>

          <VersionHistory finding={finding} />
        </div>

        <aside className="human-review-panel" aria-labelledby="human-review-heading">
          <div className="review-panel-heading">
            <p className="eyebrow">Human decision</p>
            <h2 id="human-review-heading">Record your review</h2>
            <p>This state is separate from the computational finding.</p>
          </div>

          <div className="status-separation">
            <div><small>Finding remains</small><FindingStatusBadge status={finding.status} /></div>
            <span aria-hidden="true">≠</span>
            <div><small>Review state</small><HumanReviewBadge state={finding.humanReviewState} /></div>
          </div>

          <div className="review-form">
            <label htmlFor="reviewer-name">Reviewer display name <span>(not authenticated)</span></label>
            <input id="reviewer-name" value={reviewerName} onChange={(event) => setReviewerName(event.target.value)} placeholder="Enter your name" />

            <label htmlFor="review-note">Review note</label>
            <textarea id="review-note" rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add context for the audit trail…" />

            {localError && <p className="field-error" role="alert">{localError}</p>}
            {feedback && <p className="save-feedback" role="status">✓ {feedback}</p>}

            <button className="button button-primary button-full" type="button" disabled={saving} onClick={() => void applyReviewState("REVIEWED")}>
              Mark reviewed
            </button>
            <div className="review-action-grid">
              <button className="button button-secondary" type="button" disabled={saving} onClick={() => void addNote()}>Add note</button>
              <button className="button button-secondary" type="button" disabled={saving} onClick={() => void applyReviewState("NEEDS_FOLLOW_UP", true)}>Needs follow-up</button>
              <button className="button button-secondary" type="button" disabled={saving} onClick={() => void applyReviewState("TERM_CONFIRMED")}>Confirm term</button>
              <button
                className="button button-secondary"
                type="button"
                disabled={saving || !finding.calculation || !canCorrectTerm}
                onClick={() => {
                  if (!reviewerName.trim()) {
                    setLocalError("Enter a reviewer display name before correcting a term.");
                    return;
                  }
                  setCorrectionOpen(true);
                }}
              >
                Correct term
              </button>
            </div>
            {!canCorrectTerm && (
              <p className="action-help">Term correction is unavailable for this review. Upload source evidence and rerun.</p>
            )}
          </div>

          {finding.notes.length > 0 && (
            <div className="notes-log">
              <h3>Review notes</h3>
              <ol>
                {[...finding.notes].reverse().map((item) => (
                  <li key={item.id}><p>{item.body}</p><small>{item.author} · {formatDateTime(item.createdAt)}</small></li>
                ))}
              </ol>
            </div>
          )}
        </aside>
      </div>

      {correctionOpen && (
        <CorrectionDialog
          finding={finding}
          reviewerName={reviewerName.trim()}
          saving={saving}
          onClose={() => setCorrectionOpen(false)}
          onSubmit={submitCorrection}
        />
      )}
    </div>
  );
}

function VersionHistory({ finding }: { finding: ReviewFinding }) {
  const current = finding.versions.at(-1);
  const previous = finding.versions.length > 1 ? finding.versions.at(-2) : undefined;
  return (
    <section className="detail-section version-section" aria-labelledby="version-heading">
      <div className="section-title-row">
        <div><p className="eyebrow">Change history</p><h2 id="version-heading">Review versions</h2></div>
        <span className="source-count">Version {current?.version ?? 1}</span>
      </div>
      <div className="version-grid">
        {previous && (
          <article>
            <small>Previous version</small>
            <strong>Version {previous.version}</strong>
            <span>{previous.applicableRate !== undefined ? `${previous.applicableRate}% annual fee` : "Rate unavailable"}</span>
            <span>{formatMoney(previous.expectedValue)} expected</span>
          </article>
        )}
        {current && (
          <article className="current-version">
            <small>Current version</small>
            <strong>Version {current.version}</strong>
            <span>{current.applicableRate !== undefined ? `${current.applicableRate}% annual fee` : "Rate unavailable"}</span>
            <span>{formatMoney(current.expectedValue)} expected</span>
            <p>{current.reason}</p>
          </article>
        )}
      </div>
    </section>
  );
}
