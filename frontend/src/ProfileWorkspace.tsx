import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isTerminalJob, parseRememberedJob, WorkspaceRequestError, workspaceAdapter as defaultWorkspaceAdapter } from "./api/workspaceAdapter";
import { JobProgress } from "./components/JobProgress";
import { ProfileReviewDesk } from "./components/ProfileReviewDesk";
import { RecordedReplayView } from "./components/RecordedReplayView";
import { WorkspaceIntake } from "./components/WorkspaceIntake";
import {
  buildInventory,
  inferCaseName,
  selectionIssues,
} from "./utils/folderSelection";
import type {
  BackendConnection,
  DiscoveredFile,
  FilePurpose,
  HumanReviewStatus,
  InventoryEntry,
  JobResult,
  JobStatus,
  RecordedReplay,
  StartJobResponse,
  UploadProgress,
  WorkspaceAdapter,
  WorkspaceBootstrap,
} from "./workspaceTypes";

type Screen = "INTAKE" | "PROGRESS" | "RESULT" | "REPLAY";

const checkingConnection: BackendConnection = {
  state: "UNAVAILABLE",
  label: "Checking backend",
  detail: "Verifying health, profile discovery and the UI bridge contract.",
};

interface ProfileWorkspaceProps {
  adapter?: WorkspaceAdapter;
  active?: boolean;
}

export function ProfileWorkspace({ adapter = defaultWorkspaceAdapter, active = true }: ProfileWorkspaceProps) {
  const [started, setStarted] = useState<StartJobResponse | undefined>(() => restoreAcceptedJob(adapter.sessionKey));
  const [screen, setScreen] = useState<Screen>(() => started ? "PROGRESS" : "INTAKE");
  const [bootstrap, setBootstrap] = useState<WorkspaceBootstrap>({
    connection: checkingConnection,
    profiles: [],
    replays: [],
    issues: [],
  });
  const [profileId, setProfileId] = useState(started?.profile_id ?? "");
  const [caseName, setCaseName] = useState("Untitled review pack");
  const [entries, setEntries] = useState<InventoryEntry[]>([]);
  const entriesRef = useRef<InventoryEntry[]>([]);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [checkingBackend, setCheckingBackend] = useState(true);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress>();
  const [job, setJob] = useState<JobStatus>();
  const [result, setResult] = useState<JobResult>();
  const [replay, setReplay] = useState<RecordedReplay>();
  const [pollError, setPollError] = useState<string>();
  const [reviewing, setReviewing] = useState<string>();
  const [notice, setNotice] = useState<{ tone: "success" | "info" | "error"; message: string }>();
  const submissionRef = useRef<{ signature: string; key: string } | undefined>(undefined);
  const submissionInFlight = useRef(false);
  const fetchTransactionCsv = useCallback((jobId: string, expectedSha256: string, signal?: AbortSignal) =>
    adapter.fetchTransactionCsv(jobId, expectedSha256, signal), [adapter]);

  const capabilities = bootstrap.capabilities;
  const capabilityProfile = capabilities?.profiles.find((profile) => profile.profile_id === profileId);
  const liveProfiles = useMemo(() => bootstrap.profiles.map((profile) => ({
    ...profile,
    ...deterministicPresentation(profile.id),
  })), [bootstrap.profiles]);
  const liveConnection: BackendConnection = pollError && screen === "PROGRESS" ? {
    state: "UNAVAILABLE",
    label: "Reconnecting",
    detail: "Polling is reconnecting to the accepted job; no new job will be started.",
  } : bootstrap.connection;
  const manifestIssues = useMemo(() => {
    const issues = selectionIssues(entries, capabilityProfile, capabilities?.limits);
    if (!caseName.trim()) issues.unshift("Enter a case or folder name.");
    return issues;
  }, [capabilities?.limits, capabilityProfile, caseName, entries]);

  useEffect(() => {
    let cancelled = false;
    void adapter.bootstrap().then((next) => {
      if (cancelled) return;
      setBootstrap(next);
      setCheckingBackend(false);
      const compatible = next.profiles.filter((profile) =>
        next.capabilities?.profiles.some((capability) => capability.profile_id === profile.id),
      );
      const preferred = compatible.find((profile) => profile.id === "journal-entries") ?? compatible[0];
      setProfileId((current) => compatible.some((profile) => profile.id === current) ? current : preferred?.id || "");
    }).catch((error) => {
      if (cancelled) return;
      setCheckingBackend(false);
      setBootstrap((current) => ({
        ...current,
        connection: {
          state: "UNAVAILABLE",
          label: "Backend unavailable",
          detail: "The application could not inspect the live backend contract.",
        },
        issues: [messageFrom(error)],
      }));
    });
    return () => { cancelled = true; };
  }, [adapter, connectionAttempt]);

  useEffect(() => {
    if (!active) return;
    const handle = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#profile-workspace-content h1")?.focus();
    });
    return () => window.cancelAnimationFrame(handle);
  }, [active, screen]);

  useEffect(() => {
    if (screen !== "PROGRESS" || !started) return;
    let cancelled = false;
    let timer: number | undefined;
    let failedPolls = 0;

    const poll = async () => {
      try {
        const next = await adapter.getJob(started.job_id);
        if (cancelled) return;
        failedPolls = 0;
        setPollError(undefined);
        setJob(next);
        if (isTerminalJob(next.processing_state)) {
          const completed = await adapter.getResult(started.job_id);
          if (cancelled) return;
          setResult(completed);
          setScreen("RESULT");
          return;
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof WorkspaceRequestError && (error.status === 404 || error.code === "JOB_NOT_FOUND")) {
          submissionRef.current = undefined;
          rememberAcceptedJob(adapter.sessionKey);
          setStarted(undefined);
          setJob(undefined);
          setResult(undefined);
          setPollError(undefined);
          setScreen("INTAKE");
          setNotice({
            tone: "error",
            message: entriesRef.current.some((entry) => entry.selected)
              ? "This review is no longer available on the backend. Your selected files are still here. Choose Start review to analyse them again."
              : "This saved review is no longer available on the backend. Choose the original files again to start a new review.",
          });
          return;
        }
        failedPolls += 1;
        setPollError(messageFrom(error));
      }
      const delay = Math.min(800 * 2 ** failedPolls, 5_000);
      timer = window.setTimeout(poll, delay);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [adapter, screen, started]);

  function replaceEntries(next: InventoryEntry[]) {
    entriesRef.current = next;
    setEntries(next);
  }

  function addDiscovered(discovered: DiscoveredFile[]) {
    const additions = buildInventory(discovered, capabilityProfile, capabilities?.limits, entriesRef.current);
    const next = [...entriesRef.current, ...additions];
    replaceEntries(next);
    submissionRef.current = undefined;
    if (caseName === "Untitled review pack") setCaseName(inferCaseName(next));
    const selectedCount = additions.filter((entry) => entry.selected).length;
    setNotice({
      tone: "info",
      message: `${additions.length} ${additions.length === 1 ? "entry" : "entries"} inspected; ${selectedCount} selected. Exclusions remain visible.`,
    });
  }

  function changeProfile(nextProfileId: string) {
    const nextCapability = capabilities?.profiles.find((profile) => profile.profile_id === nextProfileId);
    const discovered = entriesRef.current.map((entry) => ({
      file: entry.file,
      relativePath: entry.relativePath,
      error: entry.status === "UNREADABLE" ? entry.reason : undefined,
    }));
    setProfileId(nextProfileId);
    replaceEntries(buildInventory(discovered, nextCapability, capabilities?.limits));
    submissionRef.current = undefined;
  }

  function toggleEntry(clientFileId: string, selected: boolean) {
    replaceEntries(entriesRef.current.map((entry) => {
      if (entry.clientFileId !== clientFileId) return entry;
      if (selected && entry.status === "NEEDS_CONFIRMATION") {
        return { ...entry, selected: true, status: "SUPPORTED", reason: "Confirmed by the reviewer as an intended input." };
      }
      return { ...entry, selected };
    }));
    submissionRef.current = undefined;
  }

  function changePurpose(clientFileId: string, purpose: FilePurpose) {
    replaceEntries(entriesRef.current.map((entry) => entry.clientFileId === clientFileId ? { ...entry, purpose } : entry));
    submissionRef.current = undefined;
  }

  function removeEntry(clientFileId: string) {
    replaceEntries(entriesRef.current.filter((entry) => entry.clientFileId !== clientFileId));
    submissionRef.current = undefined;
  }

  function retryConnection() {
    setCheckingBackend(true);
    setBootstrap((current) => ({ ...current, connection: checkingConnection }));
    setConnectionAttempt((current) => current + 1);
  }

  function newReview() {
    submissionRef.current = undefined;
    rememberAcceptedJob(adapter.sessionKey);
    setStarted(undefined);
    setJob(undefined);
    setResult(undefined);
    setReplay(undefined);
    setPollError(undefined);
    setNotice(undefined);
    setScreen("INTAKE");
  }

  async function startReview() {
    if (manifestIssues.length > 0 || bootstrap.connection.state !== "CONNECTED" || busy || submissionInFlight.current) return;
    submissionInFlight.current = true;
    const selected = entriesRef.current.filter((entry) => entry.selected);
    const signature = JSON.stringify({
      profileId,
      caseName: caseName.trim(),
      files: selected.map((entry) => [entry.clientFileId, entry.relativePath, entry.sizeBytes, entry.purpose]),
    });
    const previous = submissionRef.current;
    const idempotencyKey = previous?.signature === signature ? previous.key : createId();
    submissionRef.current = { signature, key: idempotencyKey };

    setBusy(true);
    setUploadProgress(undefined);
    try {
      const next = await adapter.startJob({
        profileId,
        caseName: caseName.trim(),
        entries: entriesRef.current,
        idempotencyKey,
        onUploadProgress: setUploadProgress,
      });
      rememberAcceptedJob(adapter.sessionKey, next);
      setStarted(next);
      setJob(undefined);
      setResult(undefined);
      setPollError(undefined);
      setScreen("PROGRESS");
      setNotice(next.idempotency_reused ? {
        tone: "info",
        message: "The backend reused the existing idempotent job; no duplicate processing was launched.",
      } : undefined);
    } catch (error) {
      setNotice({ tone: "error", message: `Review was not started. ${messageFrom(error)}` });
    } finally {
      submissionInFlight.current = false;
      setBusy(false);
      setUploadProgress(undefined);
    }
  }

  async function openReplay(replayId: string) {
    setBusy(true);
    try {
      setReplay(await adapter.getReplay(replayId));
      setScreen("REPLAY");
    } catch (error) {
      setNotice({ tone: "error", message: `Recorded run could not be opened. ${messageFrom(error)}` });
    } finally {
      setBusy(false);
    }
  }

  async function updateFinding(findingId: string, reviewStatus: HumanReviewStatus) {
    if (!result || reviewing) return;
    const existingStatus = result.findings.find((finding) => finding.finding_id === findingId)?.status;
    setReviewing(findingId);
    try {
      const update = await adapter.updateFindingReview(result.job_id, findingId, reviewStatus);
      if (existingStatus && update.status !== existingStatus) {
        throw new Error("The server attempted to change the computational outcome while saving a human review state.");
      }
      setResult((current) => current ? applyReviewStatus(current, findingId, update.review_status) : current);
      setNotice({
        tone: "success",
        message: `${update.review_status.replaceAll("_", " ")} recorded. The ${update.status} check outcome is unchanged.`,
      });
    } catch (error) {
      setNotice({ tone: "error", message: `Human review state was not saved. ${messageFrom(error)}` });
    } finally {
      setReviewing(undefined);
    }
  }

  const activeMode = screen === "REPLAY" ? "RECORDED REPLAY" : "LIVE";

  return (
    <section className="profile-workspace financial-desk" aria-label="Profile workflow review">
      <header className="profile-header">
        <button
          className="brand"
          type="button"
          disabled={screen === "PROGRESS" || busy}
          title={screen === "PROGRESS" ? "Stay on this screen while the accepted job is being followed." : undefined}
          onClick={newReview}
          aria-label="Profile workflows home"
        >
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>Profile <span>workflows</span></span>
        </button>
        <div className="header-meta">
          <span className={`connection-chip connection-chip-${liveConnection.state.toLowerCase()}`}>
            <span aria-hidden="true" />{liveConnection.label}
          </span>
          <span className={`mode-label ${activeMode === "LIVE" ? "mode-live" : "mode-replay"}`}>{activeMode}</span>
          <span className="workspace-name">Folder review desk</span>
        </div>
      </header>

      <div id="profile-workspace-content" tabIndex={-1}>
        {screen === "INTAKE" && (
          <WorkspaceIntake
            connection={liveConnection}
            profiles={liveProfiles}
            capabilities={capabilities}
            capabilityProfile={capabilityProfile}
            profileId={profileId}
            caseName={caseName}
            entries={entries}
            issues={manifestIssues}
            replays={bootstrap.replays}
            busy={busy}
            uploadProgress={uploadProgress}
            checkingConnection={checkingBackend}
            onProfileChange={changeProfile}
            onCaseNameChange={(value) => { setCaseName(value); submissionRef.current = undefined; }}
            onDiscovered={addDiscovered}
            onToggle={toggleEntry}
            onPurpose={changePurpose}
            onRemove={removeEntry}
            onRetryConnection={retryConnection}
            onStart={() => void startReview()}
            onOpenReplay={(id) => void openReplay(id)}
            onNotice={(message, tone = "info") => setNotice({ tone, message })}
          />
        )}

        {screen === "PROGRESS" && started && (
          <JobProgress
            started={started}
            job={job}
            profileLabel={liveProfiles.find((profile) => profile.id === started.profile_id)?.label ?? started.profile_id}
            connection={liveConnection}
            pollError={pollError}
          />
        )}

        {screen === "RESULT" && result && (
          <ProfileReviewDesk
            result={result}
            job={job}
            profileLabel={liveProfiles.find((profile) => profile.id === result.profile_id)?.label ?? result.profile_id}
            connection={liveConnection}
            capabilities={capabilities}
            reviewing={reviewing}
            onReview={(findingId, status) => void updateFinding(findingId, status)}
            onBack={newReview}
            sourceUrl={(sourceId) => adapter.sourceUrl(result.job_id, sourceId)}
            artifactUrl={(artifactId) => adapter.artifactUrl(result.job_id, artifactId)}
            fetchTransactionCsv={fetchTransactionCsv}
            transactionCsvUrl={adapter.transactionCsvUrl(result.job_id)}
          />
        )}

        {screen === "REPLAY" && replay && (
          <RecordedReplayView
            replay={replay}
            profileLabel={bootstrap.profiles.find((profile) => profile.id === replay.profile_id)?.label ?? replay.profile_id}
            connection={bootstrap.connection}
            onBack={newReview}
          />
        )}
      </div>

      {bootstrap.issues.length > 0 && screen === "INTAKE" && (
        <details className="startup-issues">
          <summary>Backend contract diagnostics</summary>
          <ul>{bootstrap.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </details>
      )}

      {notice && (
        <div className={`toast toast-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
          <span aria-hidden="true">{notice.tone === "success" ? "✓" : notice.tone === "error" ? "!" : "i"}</span>
          <p>{notice.message}</p>
          <button type="button" aria-label="Dismiss notification" onClick={() => setNotice(undefined)}>×</button>
        </div>
      )}
    </section>
  );
}

function applyReviewStatus(result: JobResult, findingId: string, reviewStatus: HumanReviewStatus): JobResult {
  return {
    ...result,
    findings: result.findings.map((finding) =>
      finding.finding_id === findingId ? { ...finding, review_status: reviewStatus } : finding,
    ),
    documents: result.documents.map((document) => ({
      ...document,
      transaction_links: document.transaction_links.map((link) =>
        link.finding_id === findingId ? { ...link, review_status: reviewStatus } : link,
      ),
      checks: document.checks.map((check) =>
        check.finding_id === findingId ? { ...check, review_status: reviewStatus } : check,
      ),
    })),
  };
}

function createId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `submission-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function restoreAcceptedJob(sessionKey?: string): StartJobResponse | undefined {
  if (!sessionKey) return undefined;
  try {
    const saved = window.sessionStorage.getItem(sessionKey);
    if (!saved) return undefined;
    const accepted = parseRememberedJob(JSON.parse(saved));
    if (!accepted) window.sessionStorage.removeItem(sessionKey);
    return accepted;
  } catch {
    return undefined;
  }
}

function rememberAcceptedJob(sessionKey?: string, accepted?: StartJobResponse) {
  if (!sessionKey) return;
  try {
    if (accepted) window.sessionStorage.setItem(sessionKey, JSON.stringify(accepted));
    else window.sessionStorage.removeItem(sessionKey);
  } catch {
    // Processing still works when browser storage is unavailable.
  }
}

function deterministicPresentation(profileId: string): { label?: string; description?: string } {
  if (profileId === "journal-entries") return {
    label: "Bank statement validation",
    description: "Read the original statement PDFs, check their arithmetic and inspect the source evidence. A reference workbook is optional. This workflow makes no model calls and does not classify payments or generate journal entries.",
  };
  if (profileId === "pipeline-validation") return {
    label: "Statement validation package",
    description: "Run deterministic statement parsing and arithmetic checks, with a validation-package view of the source evidence. A reference workbook is optional. Model evaluation, payment resolution and classification are not run.",
  };
  return {};
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
