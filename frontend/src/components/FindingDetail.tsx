import { useMemo, useRef, useState } from "react";
import type {
  EvidenceReference,
  HumanReviewState,
  HumanReviewUpdate,
  ReviewFinding,
  ReviewResult,
  TermCorrection,
} from "../types";
import { absoluteMoneyValue, compareDecimalValues, isZeroDecimalValue } from "../utils/decimal";
import { documentRoleLabels, formatDateTime, formatDecimal, formatMoney } from "../utils/format";
import { CorrectionDialog } from "./CorrectionDialog";
import {
  ConfidenceBadge,
  FindingStatusBadge,
  HumanReviewBadge,
  SeverityBadge,
} from "./StatusBadge";

interface FindingDetailProps {
  finding: ReviewFinding;
  reviewContext: Pick<ReviewResult, "fundName" | "periodLabel" | "mode" | "version">;
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
  reviewContext,
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
    if (isZeroDecimalValue(finding.difference.amount)) return formatMoney(finding.difference);
    return `${formatMoney(absoluteMoneyValue(finding.difference))} ${
      compareDecimalValues(finding.administratorValue.amount, finding.expectedValue.amount) > 0
        ? "above reconstruction"
        : "below reconstruction"
    }`;
  }, [finding]);
  const orderedEvidence = useMemo(
    () => [...finding.evidence].sort((a, b) => evidencePriority(a) - evidencePriority(b)),
    [finding.evidence],
  );
  const commentaryLabel = reviewContext.mode === "LIVE_MODEL"
    ? "Agent commentary"
    : reviewContext.mode === "SYNTHETIC_DEMO"
      ? "Deterministic challenger commentary"
      : "Offline challenger commentary";
  const commentaryNoun = reviewContext.mode === "LIVE_MODEL" ? "Agent commentary" : "Challenger commentary";

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
          <h1 tabIndex={-1}>{finding.investorId} <span>{finding.investorName ? `${finding.investorName} · ` : ""}{finding.checkName}</span></h1>
          <p className="detail-context-line">
            {reviewContext.fundName} · {reviewContext.periodLabel} · Snapshot v{reviewContext.version} · {reviewContext.mode.replaceAll("_", " ").toLowerCase()}
          </p>
        </div>
        <div className="dual-status">
          <div><small>Finding</small><FindingStatusBadge status={finding.status} /></div>
          <div><small>Human review</small><HumanReviewBadge state={finding.humanReviewState} /></div>
          <div><small>Concern severity</small><SeverityBadge severity={finding.severity} /></div>
          <div><small>Confidence</small><ConfidenceBadge confidence={finding.confidence} /></div>
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
          <div><dt>Administrator-reported</dt><dd>{formatMoney(finding.administratorValue)}</dd><small>submitted value</small></div>
          <div><dt>Independent reconstruction</dt><dd>{formatMoney(finding.expectedValue)}</dd><small>{finding.expectedValue ? "rebuilt from governing terms" : "not established"}</small></div>
          <div className="difference-value"><dt>Difference</dt><dd>{difference}</dd><small>{finding.difference ? "absolute variance" : "cannot calculate"}</small></div>
        </dl>

        <div className="plain-explanation">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 2.5a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 6v5m0-7v.1" /></svg>
          <div><strong>Why this was flagged</strong><p>{finding.explanation}</p></div>
        </div>

        <p className="confidence-basis">
          <strong>Confidence basis:</strong> {finding.confidence?.basis ?? "No confidence assessment was supplied by the backend."}
        </p>

        {finding.requiredAction && finding.status !== "MATCH" && (
          <div className="required-action">
            <div><strong>Required action</strong><p>{finding.requiredAction.label}</p></div>
            {finding.requiredAction.documentRole && canUploadDocument ? (
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
            ) : finding.requiredAction.documentRole ? (
              <div>
                <button className="button button-secondary" type="button" disabled>Upload document</button>
                <p className="action-help">Upload is available through the live ATLAS adapter.</p>
              </div>
            ) : (
              <span className="action-guidance">Record a human disposition in the review panel below.</span>
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
              <span className="source-count">{finding.evidence.length} references · key evidence first</span>
            </div>
            {finding.evidence.length > 0 ? (
              <ul className="evidence-list">
                {orderedEvidence.map((evidence) => (
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
                      aria-label={`Inspect ${evidence.filename} evidence, ${evidence.locator}`}
                    >
                      Inspect evidence <span aria-hidden="true">→</span>
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
                  {checkLabel(check.id, check.label)}
                  <small>{check.state === "COMPLETE" ? "Completed" : check.state === "CONCERN" ? "Concern" : "Unresolved"}</small>
                </li>
              ))}
            </ul>

            {finding.verifierStatement && (
              <article className="reasoning-boundary deterministic-result">
                <span className="reasoning-icon" aria-hidden="true">✓</span>
                <div>
                  <p className="eyebrow">Deterministic verification</p>
                  <h3>Exact arithmetic and rule checks</h3>
                  <p>{plainVerificationSummary(finding)}</p>
                  <small className="verifier-technical">Verifier record: {finding.verifierStatement}</small>
                </div>
              </article>
            )}
            <article className="reasoning-boundary agent-commentary">
              <span className="reasoning-icon" aria-hidden="true">!</span>
              <div>
                <p className="eyebrow">{commentaryLabel}</p>
                <h3>Evidence-linked challenge for the reviewer</h3>
                <p>{finding.challengerConcern ?? "No additional challenger concern was recorded for this finding."}</p>
              </div>
            </article>
            <p className="reasoning-note">
              The deterministic result comes from verified inputs and exact calculation. {commentaryNoun} explains potential concerns but cannot change that result. These are observable conclusions, not private chain-of-thought.
            </p>
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
              <button
                className="button button-secondary"
                type="button"
                disabled={saving || !finding.expectedValue || !finding.calculation}
                onClick={() => void applyReviewState("TERM_CONFIRMED")}
              >
                Confirm term
              </button>
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
            {(!finding.expectedValue || !finding.calculation) && (
              <p className="action-help">Term confirmation is unavailable until source evidence establishes an independent term.</p>
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
  return (
    <section className="detail-section version-section" aria-labelledby="version-heading">
      <div className="section-title-row">
        <div><p className="eyebrow">Change history</p><h2 id="version-heading">Review versions</h2></div>
        <span className="source-count">
          {finding.versions.length} audit {finding.versions.length === 1 ? "event" : "events"}
        </span>
      </div>
      <div className="version-grid">
        {current && (current.expectedValue || current.applicableRate !== undefined) && (
          <article className="current-terms">
            <small>Current finding values</small>
            <strong>Current reconstructed terms</strong>
            <span>{current.applicableRate !== undefined ? `${formatDecimal(current.applicableRate)}% annual fee` : "Rate unavailable"}</span>
            <span>{current.expectedValue ? `${formatMoney(current.expectedValue)} expected` : "Expected value unavailable"}</span>
            <p>Shown for the current finding only; these are not claimed as values for earlier audit events.</p>
          </article>
        )}
        {finding.versions.map((version, index) => (
          <article
            className={index === finding.versions.length - 1 ? "current-version" : undefined}
            key={`${version.version}-${version.createdAt}`}
          >
            <small>{index === finding.versions.length - 1 ? "Current audit event" : "Audit event"}</small>
            <strong>Version {version.version}</strong>
            <span>Recorded {formatDateTime(version.createdAt)}</span>
            <p>{version.reason}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

const checkLabels: Record<string, string> = {
  single_proposal: "One applicable fee rule selected",
  source_complete: "Required source documents present",
  source_evidence_complete: "Source evidence supports the selected rule",
  canonical_source_references: "Source references validated",
  proposal_supported: "Reconstructed term is evidence-supported",
  reported_whole_pennies: "Administrator amount has valid penny precision",
  valid_tolerance: "Comparison tolerance is valid",
  amount_within_tolerance: "Administrator and reconstructed values agree within tolerance",
  valid_review_dates: "Review period is valid",
  valid_currency: "Currency is consistent across sources",
  claimed_expected_correct: "Reconstructed amount independently verified",
  claimed_difference_correct: "Difference independently verified",
};

function checkLabel(id: string, fallback: string): string {
  const normalizedId = id.trim().toLowerCase();
  if (checkLabels[normalizedId]) return checkLabels[normalizedId];
  const withoutPrefix = fallback.replace(/^[^:]+:\s*/, "").replace(/^Source-bound check:\s*/i, "");
  const humanized = withoutPrefix.replaceAll("_", " ").trim();
  return humanized ? humanized.charAt(0).toUpperCase() + humanized.slice(1) : "Verification check";
}

function plainVerificationSummary(finding: ReviewFinding): string {
  if (!finding.expectedValue || !finding.administratorValue || !finding.difference) {
    return "The verifier could not establish an independent value because required source evidence is incomplete.";
  }
  if (finding.status === "MATCH") {
    return `The administrator-reported ${formatMoney(finding.administratorValue)} agrees with the independently reconstructed value.`;
  }
  const direction =
    compareDecimalValues(finding.administratorValue.amount, finding.expectedValue.amount) > 0 ? "above" : "below";
  const magnitude = absoluteMoneyValue(finding.difference);
  return `Exact decimal checks reconstructed ${formatMoney(finding.expectedValue)} from the governing terms and source inputs. The administrator reported ${formatMoney(finding.administratorValue)}, leaving a ${formatMoney(magnitude)} difference ${direction} the reconstruction.`;
}

function evidencePriority(evidence: EvidenceReference): number {
  const locator = evidence.locator.toLowerCase();
  if (evidence.documentRole === "SIDE_LETTER" && locator.includes("section 3.1")) return 0;
  if (evidence.documentRole === "NAV_WORKBOOK" && /![a-z]*f\d+\b/i.test(evidence.locator)) return 1;
  if (evidence.documentRole === "INVESTOR_REGISTER" && locator.includes("fee_base")) return 2;
  if (
    evidence.documentRole === "INVESTOR_REGISTER" &&
    (locator.includes("side_letter_expected") || locator.includes("side_letter_filename"))
  ) return 3;
  if (evidence.documentRole === "LPA" && locator.includes("section 8.1")) return 4;
  if (evidence.documentRole === "INVESTOR_REGISTER" && locator.includes("investor_name")) return 5;
  return 10;
}
