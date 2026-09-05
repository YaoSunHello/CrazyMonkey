import type { EvidenceReference } from "../types";
import { documentRoleLabels } from "../utils/format";
import { Modal } from "./Modal";

export function EvidenceDialog({ evidence, onClose }: { evidence: EvidenceReference; onClose: () => void }) {
  const sourcePresentation = {
    PDF: { icon: "P", label: "Document excerpt", valueHeading: "Source text" },
    SPREADSHEET: { icon: "X", label: "Workbook cell", valueHeading: "Cell value" },
    CSV: { icon: "C", label: "CSV field", valueHeading: "Field value" },
    TEXT: { icon: "T", label: "Text excerpt", valueHeading: "Source text" },
  }[evidence.sourceKind];
  return (
    <Modal title="Source evidence" eyebrow="ATLAS source reference" onClose={onClose} size="wide">
      <div className="evidence-heading">
        <div className="file-icon" aria-hidden="true">{sourcePresentation.icon}</div>
        <div>
          <p className="evidence-filename">{evidence.filename}</p>
          <p className="muted">{documentRoleLabels[evidence.documentRole]} · {evidence.locator}</p>
        </div>
      </div>

      <dl className="evidence-metadata">
        <div><dt>Evidence ID</dt><dd><code>{evidence.id}</code></dd></div>
        <div><dt>Document role</dt><dd>{documentRoleLabels[evidence.documentRole]}</dd></div>
        <div><dt>Location</dt><dd>{evidence.locator}</dd></div>
        <div><dt>Source type</dt><dd>{sourcePresentation.label}</dd></div>
      </dl>

      <section className="source-excerpt" aria-labelledby="source-value-heading">
        <h3 id="source-value-heading">{sourcePresentation.valueHeading}</h3>
        {evidence.value ? (
          <div className="workbook-cell" role="table" aria-label="Structured evidence value">
            <div role="row" className="workbook-row workbook-header-row">
              <span role="columnheader">Location</span><span role="columnheader">Source value</span>
            </div>
            <div role="row" className="workbook-row">
              <span role="rowheader">{evidence.locator}</span><strong role="cell">{evidence.value}</strong>
            </div>
          </div>
        ) : evidence.quote ? (
          <blockquote>“{evidence.quote}”</blockquote>
        ) : (
          <p className="empty-inline">No excerpt was returned for this source.</p>
        )}
      </section>

      <section className="nearby-context" aria-labelledby="nearby-context-heading">
        <h3 id="nearby-context-heading">Nearby context</h3>
        <p>{evidence.context ?? "No nearby context was returned."}</p>
      </section>

      <p className="safe-render-note">
        <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 2.8 16 5v4.2c0 4-2.5 6.5-6 8-3.5-1.5-6-4-6-8V5l6-2.2Zm-2.6 7 1.7 1.7 3.6-3.8" /></svg>
        Displayed as structured plain text. Uploaded content cannot run scripts here.
      </p>
    </Modal>
  );
}
