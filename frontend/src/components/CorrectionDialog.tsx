import { useState, type FormEvent } from "react";
import type { ReviewFinding, TermCorrection } from "../types";
import { Modal } from "./Modal";

interface CorrectionDialogProps {
  finding: ReviewFinding;
  reviewerName: string;
  saving: boolean;
  onClose: () => void;
  onSubmit: (correction: TermCorrection) => Promise<void>;
}

export function CorrectionDialog({ finding, reviewerName, saving, onClose, onSubmit }: CorrectionDialogProps) {
  const currentRate = finding.versions.at(-1)?.applicableRate;
  const [rate, setRate] = useState(currentRate?.toString() ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const annualRate = Number(rate);
    if (!Number.isFinite(annualRate) || annualRate < 0 || annualRate > 100) {
      setError("Enter an annual percentage from 0 to 100.");
      return;
    }
    if (!reason.trim()) {
      setError("Explain why the extracted term is being corrected.");
      return;
    }
    setError(undefined);
    try {
      await onSubmit({ annualRate, note: reason.trim(), reviewerName });
    } catch {
      setError("The correction could not be saved. Check the notification for details.");
    }
  }

  return (
    <Modal
      title="Correct extracted term"
      eyebrow={`${finding.investorId} · ${finding.checkName}`}
      onClose={onClose}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="button button-primary" type="submit" form="term-correction-form" disabled={saving}>
            {saving ? <><span className="spinner" aria-hidden="true" />Creating version…</> : "Create new review version"}
          </button>
        </>
      }
    >
      <div className="correction-warning">
        <strong>This does not overwrite the original review.</strong>
        <p>The correction is sent to the review service so it can recalculate the finding and append a new version.</p>
      </div>
      <form id="term-correction-form" className="correction-form" onSubmit={(event) => void submit(event)}>
        <label htmlFor="corrected-rate">Applicable annual fee (%)</label>
        <div className="input-suffix">
          <input
            id="corrected-rate"
            type="number"
            min="0"
            max="100"
            step="0.01"
            inputMode="decimal"
            value={rate}
            onChange={(event) => setRate(event.target.value)}
            required
          />
          <span aria-hidden="true">%</span>
        </div>
        <p className="field-help">Current extracted value: {currentRate !== undefined ? `${currentRate}%` : "Unavailable"}</p>

        <label htmlFor="correction-reason">Reason for correction</label>
        <textarea
          id="correction-reason"
          rows={4}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="For example: Confirmed against signed side letter, section 4.2"
          required
        />
        <p className="field-help">Recorded under {reviewerName || "the reviewer display name"} (not authenticated).</p>
        {error && <p className="field-error" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}
