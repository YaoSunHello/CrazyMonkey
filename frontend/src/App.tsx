import { useEffect, useMemo, useState } from "react";
import { reviewAdapter as defaultReviewAdapter } from "./api/reviewAdapter";
import { EmailDialog } from "./components/EmailDialog";
import { EvidenceDialog } from "./components/EvidenceDialog";
import { FindingDetail } from "./components/FindingDetail";
import { PackWorkspace } from "./components/PackWorkspace";
import { ProcessingScreen } from "./components/ProcessingScreen";
import { ReviewSummary } from "./components/ReviewSummary";
import { StatementWorkspace } from "./components/StatementWorkspace";
import { UploadScreen } from "./components/UploadScreen";
import type {
  DetectedUpload,
  DocumentRole,
  EmailDraft,
  EvidenceReference,
  ExportFormat,
  HumanReviewUpdate,
  ReviewAdapter,
  ReviewProgress,
  ReviewResult,
  TermCorrection,
} from "./types";

type Screen = "UPLOAD" | "PROCESSING" | "SUMMARY" | "DETAIL";

const requiredRoles: DocumentRole[] = ["NAV_WORKBOOK", "LPA", "INVESTOR_REGISTER"];
const allowedExtensions = new Set(["pdf", "xlsx", "csv"]);
const maxFileSizeBytes = 25 * 1024 * 1024;

interface AppProps {
  adapter?: ReviewAdapter;
  initialWorkspace?: "STATEMENTS" | "NAV" | "PACK";
}

export function App({ adapter = defaultReviewAdapter, initialWorkspace }: AppProps) {
  const packWorkspaceEnabled = import.meta.env.VITE_ENABLE_PACK_WORKSPACE === "1";
  const [workspace, setWorkspace] = useState<"STATEMENTS" | "NAV" | "PACK">(() => {
    if (initialWorkspace) return initialWorkspace;
    const requested = new URLSearchParams(window.location.search).get("workspace")?.toLowerCase();
    if (requested === "nav") return "NAV";
    if (requested === "pack" && packWorkspaceEnabled) return "PACK";
    return "STATEMENTS";
  });
  const [screen, setScreen] = useState<Screen>("UPLOAD");
  const [documents, setDocuments] = useState<DetectedUpload[]>([]);
  const [reviewId, setReviewId] = useState<string>();
  const [progress, setProgress] = useState<ReviewProgress>();
  const [review, setReview] = useState<ReviewResult>();
  const [selectedFindingId, setSelectedFindingId] = useState<string>();
  const [evidence, setEvidence] = useState<EvidenceReference>();
  const [emailDraft, setEmailDraft] = useState<EmailDraft>();
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [exportBusy, setExportBusy] = useState<ExportFormat>();
  const [processingError, setProcessingError] = useState<string>();
  const [notice, setNotice] = useState<{ tone: "success" | "error" | "info"; message: string }>();

  const selectedFinding = useMemo(
    () => review?.findings.find((finding) => finding.id === selectedFindingId),
    [review, selectedFindingId],
  );

  const unconfirmed = documents.filter((document) => document.recognition === "NEEDS_CONFIRMATION");
  const missingRoles = requiredRoles.filter(
    (role) => !documents.some((document) => document.role === role && document.recognition === "RECOGNISED"),
  );
  const canStart =
    adapter.mode === "live" && documents.length > 0 && unconfirmed.length === 0 && missingRoles.length === 0;
  const startHelp = useMemo(() => {
    if (adapter.mode === "mock") {
      return "Uploaded-pack review is disabled in development fixture mode because Atlas is not connected. Load the synthetic demo instead.";
    }
    if (documents.length === 0) return "Add the NAV workbook, LPA and investor register to begin.";
    if (unconfirmed.length > 0) return `Confirm ${unconfirmed.length} uncertain document ${unconfirmed.length === 1 ? "role" : "roles"} before starting.`;
    if (missingRoles.length > 0) {
      const labels: Record<DocumentRole, string> = {
        NAV_WORKBOOK: "NAV workbook",
        LPA: "LPA",
        INVESTOR_REGISTER: "investor register",
        SIDE_LETTER: "side letter",
        SUPPORTING: "supporting file",
      };
      return `Still required: ${missingRoles.map((role) => labels[role]).join(", ")}.`;
    }
    return "Core documents are present. Side letters and supporting files can be included where applicable.";
  }, [adapter.mode, documents.length, missingRoles, unconfirmed.length]);

  useEffect(() => {
    const handle = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#main-content h1")?.focus();
    });
    return () => window.cancelAnimationFrame(handle);
  }, [screen, workspace]);

  useEffect(() => {
    if (screen !== "PROCESSING" || !reviewId || processingError) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const nextProgress = await adapter.getProgress(reviewId);
        if (cancelled) return;
        setProgress(nextProgress);
        if (nextProgress.state === "FAILED") {
          setProcessingError(nextProgress.error ?? "The review service reported a failure.");
          return;
        }
        if (nextProgress.state === "COMPLETE") {
          const nextReview = await adapter.getReview(reviewId);
          if (cancelled) return;
          setReview(nextReview);
          setScreen("SUMMARY");
          return;
        }
        timer = window.setTimeout(poll, adapter.mode === "mock" ? 260 : 1_000);
      } catch (error) {
        if (!cancelled) setProcessingError(messageFrom(error));
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [adapter, processingError, reviewId, screen]);

  async function selectFiles(files: File[]) {
    const validationError = validateFiles(files, documents);
    if (validationError) {
      setNotice({ tone: "error", message: validationError });
      return;
    }
    setBusy(true);
    try {
      const detected = await adapter.detectDocuments(files);
      setDocuments((existing) => [...existing, ...detected]);
      setNotice({ tone: "success", message: `${detected.length} ${detected.length === 1 ? "document" : "documents"} added.` });
    } catch (error) {
      setNotice({ tone: "error", message: messageFrom(error) });
    } finally {
      setBusy(false);
    }
  }

  function changeRole(documentId: string, role: DocumentRole) {
    setDocuments((existing) =>
      existing.map((document) =>
        document.id === documentId ? { ...document, role, recognition: "RECOGNISED" } : document,
      ),
    );
  }

  async function startUploadedReview() {
    if (!canStart) return;
    setBusy(true);
    try {
      const started = await adapter.startReview(documents);
      beginProcessing(started.reviewId);
    } catch (error) {
      setNotice({ tone: "error", message: messageFrom(error) });
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setBusy(true);
    try {
      const started = await adapter.startSyntheticReview();
      beginProcessing(started.reviewId);
    } catch (error) {
      setNotice({ tone: "error", message: messageFrom(error) });
    } finally {
      setBusy(false);
    }
  }

  function beginProcessing(id: string) {
    setReviewId(id);
    setProgress(undefined);
    setProcessingError(undefined);
    setSelectedFindingId(undefined);
    setScreen("PROCESSING");
  }

  async function updateHumanReview(update: HumanReviewUpdate) {
    if (!review || !selectedFinding) return;
    setSaving(true);
    let actionSaved = false;
    try {
      await adapter.updateHumanReview(review.id, selectedFinding.id, update);
      actionSaved = true;
      // A human action freezes a new immutable backend snapshot. Refetch the
      // whole presentation view so its version and every RELAY output stay in sync.
      setReview(await adapter.getReview(review.id));
    } catch (error) {
      const message = actionSaved
        ? `Review action was saved, but the updated review could not be loaded. ${messageFrom(error)}`
        : `Review state was not saved. ${messageFrom(error)}`;
      setNotice({ tone: "error", message });
      throw new Error(message, { cause: error });
    } finally {
      setSaving(false);
    }
  }

  async function correctTerm(correction: TermCorrection) {
    if (!review || !selectedFinding) return;
    setSaving(true);
    try {
      await adapter.correctTerm(review.id, selectedFinding.id, correction);
      setReview(await adapter.getReview(review.id));
    } catch (error) {
      setNotice({ tone: "error", message: `The correction was not recorded. ${messageFrom(error)}` });
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function uploadMissingDocument(file: File) {
    if (!review || !selectedFinding?.requiredAction?.documentRole) return;
    const validationError = validateFiles([file], []);
    if (validationError) {
      setNotice({ tone: "error", message: validationError });
      return;
    }
    setSaving(true);
    try {
      const started = await adapter.uploadSupportingDocument(
        review.id,
        file,
        selectedFinding.requiredAction.documentRole,
      );
      setNotice({ tone: "info", message: `${file.name} uploaded. The review is being prepared again.` });
      beginProcessing(started.reviewId);
    } catch (error) {
      setNotice({ tone: "error", message: `The document was not uploaded. ${messageFrom(error)}` });
    } finally {
      setSaving(false);
    }
  }

  async function requestExport(format: ExportFormat) {
    if (!review) return;
    setExportBusy(format);
    try {
      const result = await adapter.requestExport(review.id, format, review.version);
      if (!result.available || !result.blob || !result.filename) {
        setNotice({ tone: "info", message: result.message ?? `${format.toUpperCase()} output is unavailable.` });
        return;
      }
      if (adapter.mode === "live" && (result.reviewVersion === undefined || !result.snapshotSha256)) {
        throw new Error("RELAY did not return the immutable review version and snapshot hash for this export.");
      }
      if (result.reviewVersion !== undefined && result.reviewVersion !== review.version) {
        throw new Error(
          `RELAY returned snapshot v${result.reviewVersion}, but BEACON is displaying v${review.version}. Refresh the review before exporting.`,
        );
      }
      downloadBlob(result.blob, result.filename);
      const identity = result.reviewVersion !== undefined
        ? ` from RELAY snapshot v${result.reviewVersion}${result.snapshotSha256 ? ` (${result.snapshotSha256.slice(0, 10)}…)` : ""}`
        : "";
      setNotice({ tone: "success", message: `${result.filename} downloaded${identity}.` });
    } catch (error) {
      setNotice({ tone: "error", message: `The output could not be prepared. ${messageFrom(error)}` });
    } finally {
      setExportBusy(undefined);
    }
  }

  async function prepareEmail() {
    if (!review) return;
    setBusy(true);
    try {
      const draft = await adapter.prepareEmail(review.id, review.version);
      if (adapter.mode === "live" && (draft.reviewVersion === undefined || !draft.snapshotSha256)) {
        throw new Error("RELAY did not return the immutable review version and snapshot hash for this draft.");
      }
      if (draft.reviewVersion !== undefined && draft.reviewVersion !== review.version) {
        throw new Error(
          `RELAY returned draft snapshot v${draft.reviewVersion}, but BEACON is displaying v${review.version}. Refresh the review before preparing email.`,
        );
      }
      setEmailDraft(draft);
    } catch (error) {
      setNotice({ tone: "error", message: `The draft could not be prepared. ${messageFrom(error)}` });
    } finally {
      setBusy(false);
    }
  }

  async function sendEmail() {
    if (!review || !emailDraft) return;
    setSending(true);
    try {
      const result = await adapter.sendEmail(review.id, emailDraft.id);
      setNotice({ tone: result.sent ? "success" : "info", message: result.message });
      if (result.sent) setEmailDraft(undefined);
    } catch (error) {
      setNotice({ tone: "error", message: `The email was not sent. ${messageFrom(error)}` });
    } finally {
      setSending(false);
    }
  }

  async function retryProcessing() {
    if (!reviewId || retrying) return;
    setRetrying(true);
    try {
      const restarted = await adapter.retryReview(reviewId);
      beginProcessing(restarted.reviewId);
    } catch (error) {
      setProcessingError(`The review could not be restarted. ${messageFrom(error)}`);
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="#main-content" aria-label="CrazyMonkey home">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>Crazy<span>Monkey</span></span>
        </a>
        <div className="header-meta">
          <nav className="workspace-switch" aria-label="Review workspace">
            <button type="button" aria-pressed={workspace === "STATEMENTS"} onClick={() => setWorkspace("STATEMENTS")}>
              Bank statements
            </button>
            <button type="button" aria-pressed={workspace === "NAV"} onClick={() => setWorkspace("NAV")}>
              NAV review
            </button>
            {packWorkspaceEnabled && <button type="button" aria-pressed={workspace === "PACK"} onClick={() => setWorkspace("PACK")}>
              Full pack
            </button>}
          </nav>
          <span className={`mode-pill mode-${adapter.mode}`}>
            <span aria-hidden="true" />
            {workspace === "PACK"
              ? "Pack API workspace"
              : workspace === "STATEMENTS"
                ? "No fixture fallback"
              : adapter.mode === "mock"
                ? "Development fixture mode"
                : "Live adapter configured"}
          </span>
          <span className="header-divider" aria-hidden="true" />
          <span className="workspace-name">
            {workspace === "PACK" ? "Full Pack Workspace" : workspace === "STATEMENTS" ? "Bank Statement Workspace" : "NAV Review Workspace"}
          </span>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
        {workspace === "STATEMENTS" && <StatementWorkspace />}
        {packWorkspaceEnabled && workspace === "PACK" && <PackWorkspace />}
        {workspace === "NAV" && screen === "UPLOAD" && (
          <UploadScreen
            documents={documents}
            adapterMode={adapter.mode}
            busy={busy}
            canStart={canStart}
            startHelp={startHelp}
            onSelectFiles={selectFiles}
            onChangeRole={changeRole}
            onRemoveDocument={(id) => setDocuments((existing) => existing.filter((document) => document.id !== id))}
            onStart={() => void startUploadedReview()}
            onLoadDemo={() => void loadDemo()}
          />
        )}
        {workspace === "NAV" && screen === "PROCESSING" && (
          <ProcessingScreen
            progress={progress}
            error={processingError}
            retrying={retrying}
            onRetry={() => void retryProcessing()}
            onBack={() => setScreen("UPLOAD")}
          />
        )}
        {workspace === "NAV" && screen === "SUMMARY" && review && (
          <ReviewSummary
            review={review}
            exportBusy={exportBusy}
            onOpenFinding={(id) => { setSelectedFindingId(id); setScreen("DETAIL"); }}
            onExport={(format) => void requestExport(format)}
            onPrepareEmail={() => void prepareEmail()}
          />
        )}
        {workspace === "NAV" && screen === "DETAIL" && review && selectedFinding && (
          <FindingDetail
            finding={selectedFinding}
            reviewContext={review}
            saving={saving}
            onBack={() => setScreen("SUMMARY")}
            onOpenEvidence={setEvidence}
            onHumanReview={updateHumanReview}
            onCorrectTerm={correctTerm}
            onUploadDocument={uploadMissingDocument}
            canUploadDocument={adapter.mode === "live" && Boolean(selectedFinding.requiredAction?.documentRole)}
            canCorrectTerm={review.outputCapabilities.termCorrection === true}
          />
        )}
      </main>

      {workspace === "NAV" && evidence && <EvidenceDialog evidence={evidence} onClose={() => setEvidence(undefined)} />}
      {workspace === "NAV" && emailDraft && review && (
        <EmailDialog
          draft={emailDraft}
          canSend={review.outputCapabilities.emailSend}
          sending={sending}
          onClose={() => setEmailDraft(undefined)}
          onSend={sendEmail}
        />
      )}

      {workspace === "NAV" && notice && (
        <div className={`toast toast-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
          <span aria-hidden="true">{notice.tone === "success" ? "✓" : notice.tone === "error" ? "!" : "i"}</span>
          <p>{notice.message}</p>
          <button type="button" aria-label="Dismiss notification" onClick={() => setNotice(undefined)}>×</button>
        </div>
      )}
    </div>
  );
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

function validateFiles(files: File[], existing: DetectedUpload[]): string | undefined {
  const invalid = files.find((file) => {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    return !allowedExtensions.has(extension);
  });
  if (invalid) return `${invalid.name} is not supported. Use XLSX, CSV or text PDF files.`;

  const oversized = files.find((file) => file.size > maxFileSizeBytes);
  if (oversized) return `${oversized.name} exceeds the 25 MB per-file limit.`;

  const seen = new Set(existing.map((document) => `${document.filename}\u0000${document.file.size}`));
  for (const file of files) {
    const key = `${file.name}\u0000${file.size}`;
    if (seen.has(key)) return `${file.name} has already been added.`;
    seen.add(key);
  }
  return undefined;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
