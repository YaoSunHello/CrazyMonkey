import { useState } from "react";
import type { EmailDraft } from "../types";
import { Modal } from "./Modal";

interface EmailDialogProps {
  draft: EmailDraft;
  canSend: boolean;
  sending: boolean;
  onClose: () => void;
  onSend: () => Promise<void>;
}

export function EmailDialog({ draft, canSend, sending, onClose, onSend }: EmailDialogProps) {
  const [confirmed, setConfirmed] = useState(false);
  return (
    <Modal
      title="Email preview"
      eyebrow="Prepared communication"
      onClose={onClose}
      size="wide"
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={sending}>Back to review</button>
          {canSend && (
            <button
              className="button button-primary"
              type="button"
              disabled={!confirmed || sending}
              onClick={() => void onSend()}
            >
              {sending ? <><span className="spinner" aria-hidden="true" />Sending…</> : "Confirm and send"}
            </button>
          )}
        </>
      }
    >
      <div className="draft-status">
        <span aria-hidden="true">●</span>
        <div>
          <strong>Draft — not sent</strong>
          <small>{canSend ? "No message is sent unless you explicitly confirm below." : "Display-only draft; no message has been sent."}</small>
        </div>
      </div>

      <dl className="email-fields">
        <div><dt>Recipient</dt><dd>{draft.recipient || "Not selected — draft only"}</dd></div>
        <div><dt>Subject</dt><dd>{draft.subject}</dd></div>
        {draft.reviewVersion !== undefined && <div><dt>Review version</dt><dd>Snapshot v{draft.reviewVersion}</dd></div>}
        {draft.snapshotSha256 && <div><dt>Snapshot hash</dt><dd><code>{draft.snapshotSha256.slice(0, 16)}…</code></dd></div>}
      </dl>

      <section className="email-body" aria-labelledby="email-body-heading">
        <h3 id="email-body-heading">Message</h3>
        <pre>{draft.body}</pre>
      </section>

      <section className="attachment-list" aria-labelledby="attachments-heading">
        <h3 id="attachments-heading">Attachments</h3>
        <ul>
          {draft.attachments.map((attachment) => (
            <li key={attachment}><span aria-hidden="true">▱</span>{attachment}</li>
          ))}
        </ul>
      </section>

      {canSend ? (
        <label className="confirmation-check">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          <span>I have checked the recipient, message and attachments and want to send this email.</span>
        </label>
      ) : (
        <div className="integration-notice" role="note">
          <strong>Sending is unavailable</strong>
          <p>{draft.sendInstructions ?? "RELAY requires a recipient and signed preview confirmation before delivery. This draft has not been sent."}</p>
        </div>
      )}
    </Modal>
  );
}
