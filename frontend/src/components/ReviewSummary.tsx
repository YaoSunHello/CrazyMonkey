import { useMemo, useState } from "react";
import type { ExportFormat, ReviewFinding, ReviewResult } from "../types";
import { absoluteMoneyValue, compareDecimalValues, isZeroDecimalValue } from "../utils/decimal";
import { formatMoney, statusPriority } from "../utils/format";
import {
  ConfidenceBadge,
  FindingStatusBadge,
  HumanReviewBadge,
  SeverityBadge,
} from "./StatusBadge";

type Filter = "ALL" | "NEEDS_REVIEW" | "MATCHES" | "CANNOT_VERIFY" | "REVIEWED";

const filters: { value: Filter; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "NEEDS_REVIEW", label: "Needs review" },
  { value: "MATCHES", label: "Matches" },
  { value: "CANNOT_VERIFY", label: "Cannot verify" },
  { value: "REVIEWED", label: "Human-reviewed" },
];

const sourceModeLabels: Record<ReviewResult["mode"], string> = {
  SYNTHETIC_DEMO: "Synthetic source review",
  LIVE_OFFLINE: "Offline source review",
  LIVE_MODEL: "Model-assisted source review",
};

function matchesFilter(finding: ReviewFinding, filter: Filter): boolean {
  if (filter === "NEEDS_REVIEW") return finding.status !== "MATCH";
  if (filter === "MATCHES") return finding.status === "MATCH";
  if (filter === "CANNOT_VERIFY") return finding.status === "CANNOT_VERIFY";
  if (filter === "REVIEWED") return finding.humanReviewState !== "UNREVIEWED";
  return true;
}

function directionalDifference(finding: ReviewFinding): string {
  if (!finding.difference || !finding.administratorValue || !finding.expectedValue) return "—";
  if (isZeroDecimalValue(finding.difference.amount)) return formatMoney(finding.difference);
  const direction =
    compareDecimalValues(finding.administratorValue.amount, finding.expectedValue.amount) > 0 ? "above" : "below";
  return `${formatMoney(absoluteMoneyValue(finding.difference))} ${direction}`;
}

interface ReviewSummaryProps {
  review: ReviewResult;
  exportBusy?: ExportFormat;
  onOpenFinding: (findingId: string) => void;
  onExport: (format: ExportFormat) => void;
  onPrepareEmail: () => void;
}

export function ReviewSummary({
  review,
  exportBusy,
  onOpenFinding,
  onExport,
  onPrepareEmail,
}: ReviewSummaryProps) {
  const [filter, setFilter] = useState<Filter>("ALL");
  const counts = useMemo(
    () => ({
      total: review.findings.length,
      matches: review.findings.filter((finding) => finding.status === "MATCH").length,
      discrepancies: review.findings.filter((finding) => finding.status === "DISCREPANCY").length,
      cannotVerify: review.findings.filter((finding) => finding.status === "CANNOT_VERIFY").length,
      unsupported: review.findings.filter((finding) => finding.status === "UNSUPPORTED").length,
    }),
    [review.findings],
  );
  const visibleFindings = useMemo(
    () =>
      [...review.findings]
        .filter((finding) => matchesFilter(finding, filter))
        .sort((a, b) => statusPriority(a.status) - statusPriority(b.status) || a.investorId.localeCompare(b.investorId)),
    [review.findings, filter],
  );
  const exceptions = useMemo(
    () => review.findings.filter((finding) => finding.status !== "MATCH"),
    [review.findings],
  );
  const reviewedExceptions = exceptions.filter(
    (finding) => finding.humanReviewState !== "UNREVIEWED",
  );
  const pendingExceptions = exceptions
    .filter((finding) => finding.humanReviewState === "UNREVIEWED")
    .sort(
      (a, b) =>
        statusPriority(a.status) - statusPriority(b.status) ||
        a.investorId.localeCompare(b.investorId),
    );
  const nextException = pendingExceptions[0];
  const hasCompleteReviewContent = review.documents.length > 0 && review.findings.length > 0;
  const missingReviewContent = [
    review.documents.length === 0 ? "source documents" : undefined,
    review.findings.length === 0 ? "review findings" : undefined,
  ].filter((item): item is string => Boolean(item));
  const readyForRelay = hasCompleteReviewContent && pendingExceptions.length === 0;

  return (
    <div className="review-page page-enter">
      {review.source === "DEVELOPMENT_FIXTURE" && (
        <div className="fixture-banner" role="note">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 3 18 17H2L10 3Zm0 5v3.5m0 2.5v.1" /></svg>
          <div>
            <strong>{review.source === "DEVELOPMENT_FIXTURE" ? "Development fixture" : sourceModeLabels[review.mode]}</strong>
            <span>{review.sourceNotice}</span>
          </div>
        </div>
      )}

      <section className={`provenance-strip provenance-${review.source.toLowerCase()}`} aria-label="Review provenance">
        <div className="provenance-lead">
          <span className="provenance-mark" aria-hidden="true">{review.source === "ATLAS" ? "A" : "D"}</span>
          <div>
            <strong>{review.source === "ATLAS" ? "ATLAS-backed source evidence" : "Development source fixture"}</strong>
            <span>
              {review.source === "ATLAS" ? `${sourceModeLabels[review.mode]} · ` : ""}
              Deterministic verification · Immutable snapshot v{review.version}
            </span>
          </div>
        </div>
        <p>
          {review.source === "ATLAS"
            ? review.sourceNotice ?? "The result is linked to the review snapshot and its source references."
            : "Fixture-only presentation data; use the live adapter for an ATLAS-backed review."}
        </p>
      </section>

      <header className="review-header">
        <div>
          <div className="breadcrumb"><span>Reviews</span><span aria-hidden="true">/</span><span>{review.periodLabel}</span></div>
          <h1 tabIndex={-1}>Review summary</h1>
          <p>{review.fundName} <span aria-hidden="true">·</span> {review.periodLabel}</p>
        </div>
        <div className="review-context">
          <span className="review-id">Review ID <strong>{review.id}</strong></span>
          <span className="review-version">Snapshot v{review.version} · {review.mode.replaceAll("_", " ").toLowerCase()}</span>
          <span className={`plain-status ${readyForRelay ? "ready" : "pending"}`}>
            <span aria-hidden="true">{readyForRelay ? "✓" : "!"}</span>
            {!hasCompleteReviewContent
              ? "Incomplete review result"
              : readyForRelay
                ? "Ready for RELAY"
                : `${pendingExceptions.length} awaiting human review`}
          </span>
        </div>
      </header>

      <section className="summary-grid" aria-label="Review totals">
        <article className="summary-card total-card">
          <span className="summary-label">Total checks</span>
          <strong>{counts.total}</strong>
          <small>completed comparisons</small>
        </article>
        <article className="summary-card match-card">
          <span className="summary-label"><span aria-hidden="true">✓</span> Matches</span>
          <strong>{counts.matches}</strong>
          <small>agree with expected values</small>
        </article>
        <article className="summary-card discrepancy-card">
          <span className="summary-label"><span aria-hidden="true">!</span> Discrepancies</span>
          <strong>{counts.discrepancies}</strong>
          <small>need investigation</small>
        </article>
        <article className="summary-card cannot-card">
          <span className="summary-label"><span aria-hidden="true">?</span> Cannot verify</span>
          <strong>{counts.cannotVerify}</strong>
          <small>missing or insufficient evidence</small>
        </article>
      </section>

      {counts.unsupported > 0 && (
        <p className="unsupported-notice" role="note">
          {counts.unsupported} {counts.unsupported === 1 ? "check is" : "checks are"} unsupported and shown separately in the findings below.
        </p>
      )}

      {!hasCompleteReviewContent ? (
        <section className="next-exception" aria-labelledby="incomplete-result-heading">
          <div className="next-exception-copy">
            <span className="next-exception-count" aria-hidden="true">!</span>
            <div>
              <p className="eyebrow">Partial result</p>
              <h2 id="incomplete-result-heading">The backend returned an incomplete review</h2>
              <p>
                Missing {missingReviewContent.join(" and ")}. Outputs and email drafts remain locked;
                retry the review or check the source pack and backend service.
              </p>
            </div>
          </div>
        </section>
      ) : nextException ? (
        <section className="next-exception" aria-labelledby="next-exception-heading">
          <div className="next-exception-copy">
            <span className="next-exception-count" aria-hidden="true">{pendingExceptions.length}</span>
            <div>
              <p className="eyebrow">Next human decision</p>
              <h2 id="next-exception-heading">
                {pendingExceptions.length} {pendingExceptions.length === 1 ? "finding needs" : "findings need"} your review
              </h2>
              <p>
                Start with {nextException.investorName ?? nextException.investorId}: administrator-reported {formatMoney(nextException.administratorValue)} versus {formatMoney(nextException.expectedValue)} independently reconstructed. {nextException.difference ? `Difference: ${directionalDifference(nextException)} the reconstruction.` : "Evidence is incomplete, so no independent value can be established."}
              </p>
            </div>
          </div>
          <button className="button button-primary" type="button" onClick={() => onOpenFinding(nextException.id)}>
            Review next exception <span aria-hidden="true">→</span>
          </button>
        </section>
      ) : (
        <section className="next-exception next-exception-complete" aria-label="Human review complete">
          <div className="next-exception-copy">
            <span className="next-exception-count" aria-hidden="true">✓</span>
            <div><p className="eyebrow">Human review complete</p><h2>All exceptions have a recorded disposition</h2><p>The deterministic findings remain unchanged. RELAY outputs are now available for this snapshot.</p></div>
          </div>
        </section>
      )}

      <section className="findings-section" aria-labelledby="findings-heading">
        <div className="findings-heading-row">
          <div>
            <p className="eyebrow">Exception-led review</p>
            <h2 id="findings-heading">Findings</h2>
            <p>Open a finding to trace the calculation and source evidence.</p>
          </div>
          <span className="results-count" aria-live="polite">{visibleFindings.length} {visibleFindings.length === 1 ? "result" : "results"}</span>
        </div>

        <div className="filter-bar" role="group" aria-label="Filter findings">
          {filters.map((item) => {
            const count = review.findings.filter((finding) => matchesFilter(finding, item.value)).length;
            return (
              <button
                key={item.value}
                type="button"
                className={filter === item.value ? "active" : ""}
                aria-pressed={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}<span>{count}</span>
              </button>
            );
          })}
        </div>
        <p className="filter-help">Needs review includes every computational non-match, even after a person has reviewed it.</p>

        <div className="table-wrap" role="region" aria-label="Review findings table, horizontally scrollable" tabIndex={0}>
          <table className="findings-table">
            <caption className="visually-hidden">Review findings by investor</caption>
            <thead>
              <tr>
                <th scope="col">Investor</th>
                <th scope="col" className="numeric">Administrator-reported</th>
                <th scope="col" className="numeric">Independent reconstruction</th>
                <th scope="col" className="numeric">Difference</th>
                <th scope="col">Finding</th>
                <th scope="col">Concern severity / confidence</th>
                <th scope="col">Review state</th>
                <th scope="col"><span className="visually-hidden">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {visibleFindings.map((finding) => (
                <tr key={finding.id} className={`finding-row row-${finding.status.toLowerCase().replace("_", "-")}`}>
                  <th scope="row">
                    <span className="investor-avatar" aria-hidden="true">{finding.investorId.slice(-2)}</span>
                    <span className="investor-cell-copy">
                      <strong>{finding.investorName ?? finding.investorId}</strong>
                      <small>{finding.investorName ? `${finding.investorId} · ` : ""}{finding.checkName}</small>
                    </span>
                  </th>
                  <td className="numeric strong-number">{formatMoney(finding.administratorValue)}</td>
                  <td className="numeric">{formatMoney(finding.expectedValue)}</td>
                  <td className="numeric difference-cell">{directionalDifference(finding)}</td>
                  <td><FindingStatusBadge status={finding.status} /></td>
                  <td><div className="risk-stack"><SeverityBadge severity={finding.severity} /><ConfidenceBadge confidence={finding.confidence} /></div></td>
                  <td><HumanReviewBadge state={finding.humanReviewState} /></td>
                  <td className="open-cell">
                    <button className="row-open-button" type="button" onClick={() => onOpenFinding(finding.id)} aria-label={`Review ${finding.investorId} ${finding.checkName} finding`}>
                      Review finding <span aria-hidden="true">→</span>
                    </button>
                  </td>
                </tr>
              ))}
              {visibleFindings.length === 0 && (
                <tr><td colSpan={8} className="empty-table">No findings match this filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="outputs-section" aria-labelledby="outputs-heading">
        <div>
          <p className="eyebrow">Immutable handoff</p>
          <h2 id="outputs-heading">RELAY outputs</h2>
          <p>Export the reviewed audit trail or prepare a draft for the operations team.</p>
          <span className={`relay-readiness ${readyForRelay ? "ready" : "pending"}`}>
            {reviewedExceptions.length} of {exceptions.length} exceptions reviewed
          </span>
        </div>
        <div className="output-actions">
          <OutputButton label="PDF report" enabled={readyForRelay && review.outputCapabilities.pdf} busy={exportBusy === "pdf"} onClick={() => onExport("pdf")} />
          <OutputButton label="Excel review" enabled={readyForRelay && review.outputCapabilities.excel} busy={exportBusy === "excel"} onClick={() => onExport("excel")} />
          <OutputButton label="JSON audit package" enabled={readyForRelay && review.outputCapabilities.json} busy={exportBusy === "json"} onClick={() => onExport("json")} />
          <button className="button button-primary" type="button" onClick={onPrepareEmail} disabled={!readyForRelay || !review.outputCapabilities.emailPrepare}>
            Prepare email <span aria-hidden="true">→</span>
          </button>
        </div>
        <p className="output-note" role="note">
          {!readyForRelay
            ? !hasCompleteReviewContent
              ? `RELAY remains locked because the review is missing ${missingReviewContent.join(" and ")}.`
              : `Record a human disposition for ${pendingExceptions.length} remaining ${pendingExceptions.length === 1 ? "exception" : "exceptions"} to unlock RELAY.`
            : !review.outputCapabilities.pdf || !review.outputCapabilities.excel
              ? "Unavailable formats are awaiting RELAY integration in this build."
              : "Outputs use the displayed immutable review snapshot. Email opens as a draft and is not sent."}
        </p>
      </section>
    </div>
  );
}

function OutputButton({ label, enabled, busy, onClick }: { label: string; enabled: boolean; busy: boolean; onClick: () => void }) {
  return (
    <button
      className="button button-secondary"
      type="button"
      onClick={onClick}
      disabled={!enabled || busy}
      aria-label={label}
    >
      {busy ? <><span className="spinner" aria-hidden="true" />Preparing…</> : <><span className="download-icon" aria-hidden="true">↓</span>{label}</>}
    </button>
  );
}
