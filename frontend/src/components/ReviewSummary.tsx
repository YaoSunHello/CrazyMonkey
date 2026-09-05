import { useMemo, useState } from "react";
import type { ExportFormat, ReviewFinding, ReviewResult } from "../types";
import { formatMoney, statusPriority } from "../utils/format";
import { FindingStatusBadge, HumanReviewBadge } from "./StatusBadge";

type Filter = "ALL" | "NEEDS_REVIEW" | "MATCHES" | "CANNOT_VERIFY" | "REVIEWED";

const filters: { value: Filter; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "NEEDS_REVIEW", label: "Needs review" },
  { value: "MATCHES", label: "Matches" },
  { value: "CANNOT_VERIFY", label: "Cannot verify" },
  { value: "REVIEWED", label: "Reviewed" },
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
  if (filter === "REVIEWED") return finding.humanReviewState === "REVIEWED";
  return true;
}

function directionalDifference(finding: ReviewFinding): string {
  if (!finding.difference || !finding.administratorValue || !finding.expectedValue) return "—";
  if (finding.difference.amount === 0) return formatMoney(finding.difference);
  const direction =
    finding.administratorValue.amount > finding.expectedValue.amount ? "over" : "under";
  return `${formatMoney(finding.difference)} ${direction}`;
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

  return (
    <div className="review-page page-enter">
      {(review.source === "DEVELOPMENT_FIXTURE" || review.sourceNotice) && (
        <div className="fixture-banner" role="note">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 3 18 17H2L10 3Zm0 5v3.5m0 2.5v.1" /></svg>
          <div>
            <strong>{review.source === "DEVELOPMENT_FIXTURE" ? "Development fixture" : sourceModeLabels[review.mode]}</strong>
            <span>{review.sourceNotice}</span>
          </div>
        </div>
      )}

      <header className="review-header">
        <div>
          <div className="breadcrumb"><span>Reviews</span><span aria-hidden="true">/</span><span>{review.periodLabel}</span></div>
          <h1 tabIndex={-1}>Review summary</h1>
          <p>{review.fundName} <span aria-hidden="true">·</span> {review.periodLabel}</p>
        </div>
        <div className="review-context">
          <span className="review-id">Review ID <strong>{review.id}</strong></span>
          <span className="plain-status"><span aria-hidden="true">✓</span> Review prepared</span>
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

        <div className="table-wrap">
          <table className="findings-table">
            <caption className="visually-hidden">Review findings by investor</caption>
            <thead>
              <tr>
                <th scope="col">Investor</th>
                <th scope="col">Check</th>
                <th scope="col" className="numeric">Administrator</th>
                <th scope="col" className="numeric">Expected</th>
                <th scope="col" className="numeric">Difference</th>
                <th scope="col">Status</th>
                <th scope="col">Review state</th>
                <th scope="col"><span className="visually-hidden">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {visibleFindings.map((finding) => (
                <tr key={finding.id} className={`finding-row row-${finding.status.toLowerCase().replace("_", "-")}`}>
                  <th scope="row"><span className="investor-avatar" aria-hidden="true">{finding.investorId.slice(-2)}</span>{finding.investorId}</th>
                  <td>{finding.checkName}</td>
                  <td className="numeric strong-number">{formatMoney(finding.administratorValue)}</td>
                  <td className="numeric">{formatMoney(finding.expectedValue)}</td>
                  <td className="numeric difference-cell">{directionalDifference(finding)}</td>
                  <td><FindingStatusBadge status={finding.status} /></td>
                  <td><HumanReviewBadge state={finding.humanReviewState} /></td>
                  <td className="open-cell">
                    <button className="row-open-button" type="button" onClick={() => onOpenFinding(finding.id)} aria-label={`Open ${finding.investorId} ${finding.checkName} finding`}>
                      Open <span aria-hidden="true">→</span>
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
          <p className="eyebrow">Review outputs</p>
          <h2 id="outputs-heading">Share the review</h2>
          <p>Export the audit trail or prepare a draft for the operations team.</p>
        </div>
        <div className="output-actions">
          <OutputButton label="PDF report" enabled={review.outputCapabilities.pdf} busy={exportBusy === "pdf"} onClick={() => onExport("pdf")} />
          <OutputButton label="Excel review" enabled={review.outputCapabilities.excel} busy={exportBusy === "excel"} onClick={() => onExport("excel")} />
          <OutputButton label="JSON audit package" enabled={review.outputCapabilities.json} busy={exportBusy === "json"} onClick={() => onExport("json")} />
          <button className="button button-primary" type="button" onClick={onPrepareEmail} disabled={!review.outputCapabilities.emailPrepare}>
            Prepare email <span aria-hidden="true">→</span>
          </button>
        </div>
        {(!review.outputCapabilities.pdf || !review.outputCapabilities.excel) && (
          <p className="output-note">Unavailable formats are awaiting Relay integration in this build.</p>
        )}
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
      title={!enabled ? "Output service not connected in this build" : undefined}
    >
      {busy ? <><span className="spinner" aria-hidden="true" />Preparing…</> : <><span className="download-icon" aria-hidden="true">↓</span>{label}</>}
    </button>
  );
}
