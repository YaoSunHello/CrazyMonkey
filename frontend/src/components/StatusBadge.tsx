import type {
  FindingConfidence,
  FindingSeverity,
  FindingStatus,
  HumanReviewState,
} from "../types";
import { findingStatusLabels, humanReviewLabels } from "../utils/format";

function StatusMark({ kind }: { kind: "check" | "alert" | "question" | "review" | "follow" | "term" }) {
  const path = {
    check: "M4 10.5 8.2 14.5 16.5 5.8",
    alert: "M10 5.5v5M10 14.2v.1",
    question: "M7.7 7.3A2.5 2.5 0 0 1 10 5.8c1.5 0 2.6.9 2.6 2.2 0 1.8-2.6 2-2.6 3.7M10 14.5v.1",
    review: "M5.5 10.3 8.5 13l6-6.3",
    follow: "M10 5.5v5M10 14.2v.1",
    term: "M5.5 10.3 8.5 13l6-6.3",
  }[kind];

  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="status-icon">
      <circle cx="10" cy="10" r="7.6" />
      <path d={path} />
    </svg>
  );
}

export function FindingStatusBadge({ status }: { status: FindingStatus }) {
  const icon =
    status === "MATCH" ? "check" : status === "CANNOT_VERIFY" ? "question" : "alert";
  return (
    <span className={`status-badge status-${status.toLowerCase().replace("_", "-")}`}>
      <StatusMark kind={icon} />
      {findingStatusLabels[status]}
    </span>
  );
}

export function HumanReviewBadge({ state }: { state: HumanReviewState }) {
  const icon = state === "NEEDS_FOLLOW_UP" ? "follow" : state === "TERM_CONFIRMED" ? "term" : "review";
  return (
    <span className={`review-badge review-${state.toLowerCase().replaceAll("_", "-")}`}>
      <StatusMark kind={icon} />
      {humanReviewLabels[state]}
    </span>
  );
}

const severityLabels: Record<FindingSeverity, string> = {
  NONE: "Not assigned",
  INFO: "Info",
  WARNING: "Warning",
  CRITICAL: "Critical",
};

export function SeverityBadge({ severity = "NONE" }: { severity?: FindingSeverity }) {
  const icon = severity === "NONE" || severity === "INFO" ? "question" : "alert";
  return (
    <span className={`severity-badge severity-${severity.toLowerCase()}`}>
      <StatusMark kind={icon} />
      {severityLabels[severity]}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence?: FindingConfidence }) {
  const label = confidence?.label ?? "NOT_SCORED";
  const display = {
    HIGH: "High confidence",
    MEDIUM: "Medium confidence",
    LOW: "Low confidence",
    NOT_SCORED: "Not scored",
  }[label];
  return (
    <span className={`confidence-badge confidence-${label.toLowerCase().replace("_", "-")}`}>
      <StatusMark kind={label === "NOT_SCORED" ? "question" : label === "LOW" ? "alert" : "check"} />
      {display}
    </span>
  );
}
