import type {
  BackendProfileSummary,
  BridgeCapabilities,
  FindingReviewResponse,
  HumanReviewStatus,
  JobResult,
  JobStatus,
  RecordedReplay,
  ReplayList,
  StartJobRequest,
  StartJobResponse,
  WorkspaceAdapter,
  WorkspaceBootstrap,
} from "../workspaceTypes";

const terminalStates = new Set(["SUCCEEDED", "PARTIAL", "FAILED"]);

export class WorkspaceRequestError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "WorkspaceRequestError";
  }
}

export class HttpWorkspaceAdapter implements WorkspaceAdapter {
  readonly mode = "live" as const;
  readonly sessionKey: string;
  private readonly baseUrl: string;

  constructor(baseUrl = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.sessionKey = `crazymonkey.ui.v1.job:${this.baseUrl || "same-origin"}`;
  }

  async bootstrap(): Promise<WorkspaceBootstrap> {
    const [healthResult, profilesResult, capabilitiesResult, replaysResult] = await Promise.allSettled([
      this.fetchJson<unknown>("/health"),
      this.fetchJson<unknown>("/api/profiles"),
      this.fetchJson<unknown>("/api/ui/v1/capabilities"),
      this.fetchJson<unknown>("/api/ui/v1/replays"),
    ]);

    const issues: string[] = [];
    const healthOk = healthResult.status === "fulfilled" && isRecord(healthResult.value) && healthResult.value.status === "ok";

    let profiles: BackendProfileSummary[] = [];
    if (profilesResult.status === "fulfilled") {
      try {
        profiles = requireProfiles(profilesResult.value);
      } catch (error) {
        issues.push(messageFrom(error));
      }
    } else {
      issues.push(`Profile discovery failed: ${messageFrom(profilesResult.reason)}`);
    }

    let capabilities: BridgeCapabilities | undefined;
    if (capabilitiesResult.status === "fulfilled") {
      try {
        capabilities = requireCapabilities(capabilitiesResult.value);
      } catch (error) {
        issues.push(messageFrom(error));
      }
    } else {
      issues.push(`UI bridge unavailable: ${messageFrom(capabilitiesResult.reason)}`);
    }

    let replays: ReplayList["replays"] = [];
    if (replaysResult.status === "fulfilled") {
      try {
        replays = requireReplayList(replaysResult.value).replays;
      } catch (error) {
        issues.push(messageFrom(error));
      }
    } else {
      issues.push(`Recorded runs unavailable: ${messageFrom(replaysResult.reason)}`);
    }

    if (!healthOk) issues.unshift("Backend health check failed.");

    const profileIds = new Set(profiles.map((profile) => profile.id));
    const capabilityIds = new Set(capabilities?.profiles.map((profile) => profile.profile_id) ?? []);
    const capabilityProfiles = capabilities?.profiles ?? [];
    const contractAligned = capabilityProfiles.length > 0
      && profileIds.size === profiles.length
      && capabilityIds.size === capabilityProfiles.length
      && [...capabilityIds].every((id) => profileIds.has(id));
    const compatibleProfiles = profiles.filter((profile) => capabilityIds.has(profile.id));
    if (capabilities && !contractAligned) {
      issues.push("UI bridge capabilities advertise an unknown or duplicate workflow.");
    }

    if (healthOk && capabilities && contractAligned) {
      return {
        connection: {
          state: "CONNECTED",
          label: "Backend connected",
          detail: `${capabilities.execution.label} · ${capabilities.execution.model_calls} model calls`,
        },
        profiles: compatibleProfiles,
        capabilities,
        replays,
        issues,
      };
    }

    if (healthOk) {
      return {
        connection: {
          state: "HEALTH_ONLY",
          label: "Health only",
          detail: "The server answered /health, but the review bridge contract is unavailable or incompatible.",
        },
        profiles,
        capabilities,
        replays,
        issues,
      };
    }

    return {
      connection: {
        state: "UNAVAILABLE",
        label: "Backend unavailable",
        detail: "No live processing request will be attempted until the backend and UI bridge respond.",
      },
      profiles,
      capabilities,
      replays,
      issues,
    };
  }

  async startJob(request: StartJobRequest): Promise<StartJobResponse> {
    const entries = request.entries.filter((entry) => entry.selected);
    if (entries.length === 0) throw new Error("Select at least one source file before starting review.");
    if (entries.some((entry) => !entry.file || !entry.purpose)) {
      throw new Error("The selected manifest contains a file that cannot be uploaded.");
    }

    const manifest = {
      profile_id: request.profileId,
      case_name: request.caseName,
      files: entries.map((entry) => ({
        client_file_id: entry.clientFileId,
        relative_path: entry.relativePath,
        filename: entry.filename,
        size_bytes: entry.sizeBytes,
        content_type: entry.contentType,
        selection_status: "SELECTED",
        purpose: entry.purpose,
      })),
    };

    const form = new FormData();
    form.append("manifest", JSON.stringify(manifest));
    for (const entry of entries) {
      const selectedFile = entry.file as File;
      const uploadFile = selectedFile.type
        ? selectedFile
        : new File([selectedFile], entry.filename, {
          type: entry.contentType,
          lastModified: selectedFile.lastModified,
        });
      form.append("files", uploadFile, entry.filename);
    }

    const payload = request.onUploadProgress && typeof XMLHttpRequest !== "undefined"
      ? await this.postJobWithUploadProgress(form, request.idempotencyKey, request.onUploadProgress)
      : await this.fetchJson<unknown>("/api/ui/v1/jobs", {
        method: "POST",
        headers: { "Idempotency-Key": request.idempotencyKey },
        body: form,
      });
    return requireStartJob(payload, request.profileId, request.caseName);
  }

  private postJobWithUploadProgress(
    form: FormData,
    idempotencyKey: string,
    onProgress: NonNullable<StartJobRequest["onUploadProgress"]>,
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      let measuredTotal = 0;
      request.open("POST", `${this.baseUrl}/api/ui/v1/jobs`);
      request.setRequestHeader("Idempotency-Key", idempotencyKey);
      request.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable || event.total <= 0) return;
        measuredTotal = event.total;
        onProgress({
          loadedBytes: Math.min(event.loaded, event.total),
          totalBytes: event.total,
          percentage: Math.min(100, Math.round((event.loaded / event.total) * 100)),
        });
      });
      request.addEventListener("load", () => {
        let payload: unknown;
        try {
          payload = JSON.parse(request.responseText);
        } catch (error) {
          reject(new Error("The backend returned invalid JSON.", { cause: error }));
          return;
        }
        if (request.status < 200 || request.status >= 300) {
          reject(requestErrorFromPayload(payload, request.status));
          return;
        }
        if (measuredTotal > 0) {
          onProgress({ loadedBytes: measuredTotal, totalBytes: measuredTotal, percentage: 100 });
        }
        resolve(payload);
      });
      request.addEventListener("error", () => reject(new Error("Could not reach the backend during upload.")));
      request.addEventListener("abort", () => reject(new Error("The upload was aborted before the backend accepted it.")));
      request.send(form);
    });
  }

  async getJob(jobId: string): Promise<JobStatus> {
    const payload = await this.fetchJson<unknown>(`/api/ui/v1/jobs/${encodeURIComponent(jobId)}`);
    return requireJobStatus(payload, jobId);
  }

  async getResult(jobId: string): Promise<JobResult> {
    const payload = await this.fetchJson<unknown>(`/api/ui/v1/jobs/${encodeURIComponent(jobId)}/result`);
    return requireJobResult(payload, jobId);
  }

  async updateFindingReview(
    jobId: string,
    findingId: string,
    reviewStatus: HumanReviewStatus,
  ): Promise<FindingReviewResponse> {
    const payload = await this.fetchJson<unknown>(
      `/api/ui/v1/jobs/${encodeURIComponent(jobId)}/findings/${encodeURIComponent(findingId)}/review`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_status: reviewStatus }),
      },
    );
    return requireReviewResponse(payload, jobId, findingId);
  }

  async getReplay(replayId: string): Promise<RecordedReplay> {
    const payload = await this.fetchJson<unknown>(`/api/ui/v1/replays/${encodeURIComponent(replayId)}`);
    return requireReplay(payload, replayId);
  }

  sourceUrl(jobId: string, sourceId: string): string {
    return `${this.baseUrl}/api/ui/v1/jobs/${encodeURIComponent(jobId)}/sources/${encodeURIComponent(sourceId)}`;
  }

  artifactUrl(jobId: string, artifactId: string): string {
    return `${this.baseUrl}/api/ui/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`;
  }

  private async fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
    } catch (error) {
      throw new Error(`Could not reach the backend. ${messageFrom(error)}`, { cause: error });
    }
    if (!response.ok) throw await responseError(response);
    try {
      return (await response.json()) as T;
    } catch (error) {
      throw new Error("The backend returned invalid JSON.", { cause: error });
    }
  }
}

export const workspaceAdapter: WorkspaceAdapter = new HttpWorkspaceAdapter(
  import.meta.env.VITE_API_BASE_URL ?? "",
);

export function isTerminalJob(state: JobStatus["processing_state"]): boolean {
  return terminalStates.has(state);
}

export function parseRememberedJob(value: unknown): StartJobResponse | undefined {
  if (!isRecord(value) || !isText(value.profile_id) || !isText(value.case_name)) return undefined;
  try {
    return requireStartJob(value, value.profile_id, value.case_name);
  } catch {
    return undefined;
  }
}

function requireProfiles(value: unknown): BackendProfileSummary[] {
  if (!Array.isArray(value) || !value.every(isProfile)) {
    throw new Error("GET /api/profiles returned an incompatible profile contract.");
  }
  return value;
}

function isProfile(value: unknown): value is BackendProfileSummary {
  return isRecord(value)
    && isText(value.id)
    && isText(value.label)
    && typeof value.description === "string"
    && typeof value.documents === "string"
    && isStringArray(value.tables)
    && isStringArray(value.passes)
    && isStringArray(value.envelope);
}

function requireCapabilities(value: unknown): BridgeCapabilities {
  if (!isRecord(value)
    || value.api_version !== "ui.v1"
    || !isRecord(value.execution)
    || value.execution.label !== "LOCAL_DETERMINISTIC"
    || !isNonNegativeInteger(value.execution.model_calls)
    || typeof value.execution.browser_commands_executed !== "boolean"
    || !isLimits(value.limits)
    || !Array.isArray(value.profiles)
    || !value.profiles.every(isCapabilityProfile)
    || !isArtifactsCapability(value.artifacts)
    || !Array.isArray(value.review_statuses)
    || !value.review_statuses.every(isReviewStatus)) {
    throw new Error("GET /api/ui/v1/capabilities returned an incompatible contract.");
  }
  return value as unknown as BridgeCapabilities;
}

function requireReplayList(value: unknown): ReplayList {
  if (!isRecord(value)
    || !Array.isArray(value.replays)
    || !value.replays.every(isReplaySummary)
    || typeof value.note !== "string") {
    throw new Error("The replay list returned an incompatible contract.");
  }
  return value as unknown as ReplayList;
}

function requireStartJob(
  value: unknown,
  expectedProfileId: string,
  expectedCaseName: string,
): StartJobResponse {
  if (!isRecord(value)
    || !isText(value.job_id)
    || !isText(value.profile_id)
    || !isText(value.case_name)
    || value.profile_id !== expectedProfileId
    || value.case_name !== expectedCaseName
    || value.execution_label !== "LOCAL_DETERMINISTIC"
    || !isProcessingState(value.processing_state)
    || typeof value.idempotency_reused !== "boolean"
    || !hasLinks(value.links, ["status", "result"])) {
    throw new Error("The job-start response is incompatible with UI bridge v1.");
  }
  return value as unknown as StartJobResponse;
}

function requireJobStatus(value: unknown, expectedJobId: string): JobStatus {
  if (!isRecord(value)
    || !isText(value.job_id)
    || value.job_id !== expectedJobId
    || !isProcessingState(value.processing_state)
    || !Array.isArray(value.documents)
    || !value.documents.every(isJobDocument)
    || !Array.isArray(value.events)
    || !value.events.every(isJobEvent)
    || !isEventTrace(value.event_trace)
    || !hasLinks(value.links, ["result"])) {
    throw new Error("The job-status response is incompatible with UI bridge v1.");
  }
  return value as unknown as JobStatus;
}

function requireJobResult(value: unknown, expectedJobId: string): JobResult {
  if (!isRecord(value)
    || !isText(value.job_id)
    || value.job_id !== expectedJobId
    || !isText(value.profile_id)
    || !isText(value.case_name)
    || value.execution_label !== "LOCAL_DETERMINISTIC"
    || !isProcessingState(value.processing_state)
    || !isResultSummary(value.summary)
    || !isReferenceValidation(value.reference_validation)
    || !Array.isArray(value.documents)
    || !value.documents.every(isResultDocument)
    || !Array.isArray(value.findings)
    || !value.findings.every(isResultFinding)
    || !Array.isArray(value.artifacts)
    || !value.artifacts.every(isResultArtifact)
    || !isRecord(value.agent_resolution)
    || value.agent_resolution.status !== "NOT_RUN"
    || !isText(value.agent_resolution.reason)
    || !isRecord(value.profile_projection)
    || !["AVAILABLE", "OMITTED"].includes(String(value.profile_projection.status))) {
    throw new Error("The result response is incompatible with UI bridge v1.");
  }
  if (value.error !== undefined && typeof value.error !== "string") {
    throw new Error("The result response contains an incompatible terminal error.");
  }
  return value as unknown as JobResult;
}

function requireReviewResponse(
  value: unknown,
  expectedJobId: string,
  expectedFindingId: string,
): FindingReviewResponse {
  if (!isRecord(value)
    || !isText(value.job_id)
    || !isText(value.finding_id)
    || value.job_id !== expectedJobId
    || value.finding_id !== expectedFindingId
    || !isOutcome(value.status)
    || !isReviewStatus(value.review_status)
    || !isText(value.updated_at)) {
    throw new Error("The human-review response is incompatible with UI bridge v1.");
  }
  return value as unknown as FindingReviewResponse;
}

function requireReplay(value: unknown, expectedReplayId: string): RecordedReplay {
  if (!isReplaySummary(value)
    || !isRecord(value)
    || value.replay_id !== expectedReplayId
    || !Array.isArray(value.accounts)
    || !value.accounts.every(isReplayAccount)
    || !isRecord(value.timing)
    || value.timing.mode !== "RECORDED_SECONDS"
    || value.timing.compression_performed !== false
    || value.model_calls !== 0
    || value.event_trace_available !== false) {
    throw new Error("The recorded-run response is incompatible with UI bridge v1.");
  }
  return value as unknown as RecordedReplay;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isProcessingState(value: unknown): boolean {
  return typeof value === "string" && ["QUEUED", "PROCESSING", "SUCCEEDED", "PARTIAL", "FAILED"].includes(value);
}

function isOutcome(value: unknown): boolean {
  return typeof value === "string" && ["PASS", "FAIL", "UNRESOLVED"].includes(value);
}

function isReviewStatus(value: unknown): boolean {
  return typeof value === "string" && ["UNREVIEWED", "REVIEWED", "NEEDS_FOLLOW_UP"].includes(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveInteger(value: unknown): value is number {
  return isNonNegativeInteger(value) && value > 0;
}

function isLimits(value: unknown): boolean {
  return isRecord(value)
    && isPositiveInteger(value.max_files)
    && isPositiveInteger(value.max_file_bytes)
    && isPositiveInteger(value.max_batch_bytes)
    && isPositiveInteger(value.max_path_depth)
    && isPositiveInteger(value.max_events_per_job);
}

function isCapabilityFormat(value: unknown): boolean {
  return isRecord(value)
    && typeof value.extension === "string"
    && value.extension.startsWith(".")
    && isStringArray(value.content_types);
}

function isCapabilityProfile(value: unknown): boolean {
  if (!isRecord(value)
    || !isText(value.profile_id)
    || !isText(value.label)
    || typeof value.description !== "string"
    || !isRecord(value.source)
    || !isRecord(value.reference)) return false;
  return value.source.purpose === "SOURCE"
    && typeof value.source.required === "boolean"
    && Array.isArray(value.source.formats)
    && value.source.formats.every(isCapabilityFormat)
    && value.reference.purpose === "REFERENCE"
    && typeof value.reference.required === "boolean"
    && isNonNegativeInteger(value.reference.max_files)
    && Array.isArray(value.reference.formats)
    && value.reference.formats.every(isCapabilityFormat)
    && Array.isArray(value.reference.tables);
}

function isArtifactsCapability(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return [value.json, value.report, value.workbook].every((item) => (
    isRecord(item)
    && typeof item.available === "boolean"
    && (item.reason === undefined || typeof item.reason === "string")
  ));
}

function hasLinks(value: unknown, keys: string[]): boolean {
  return isRecord(value) && keys.every((key) => isText(value[key]));
}

function isFilePurpose(value: unknown): boolean {
  return value === "SOURCE" || value === "REFERENCE";
}

function isDocumentState(value: unknown): boolean {
  return typeof value === "string" && ["PENDING", "PROCESSING", "SUCCEEDED", "FAILED"].includes(value);
}

function isJobDocument(value: unknown): boolean {
  return isRecord(value)
    && isText(value.source_id)
    && isText(value.client_file_id)
    && isText(value.relative_path)
    && isText(value.filename)
    && isFilePurpose(value.purpose)
    && isDocumentState(value.processing_state)
    && (value.computational_outcome === null || isOutcome(value.computational_outcome))
    && (value.error === undefined || value.error === null || typeof value.error === "string");
}

function isJobEvent(value: unknown): boolean {
  return isRecord(value)
    && typeof value.kind === "string"
    && ["think", "tool", "code", "stdout", "stderr", "verdict", "state", "result"].includes(value.kind)
    && typeof value.label === "string"
    && typeof value.detail === "string"
    && typeof value.status === "string"
    && ["running", "ok", "fail", "skip"].includes(value.status)
    && typeof value.body === "string"
    && isRecord(value.meta)
    && typeof value.at === "number"
    && Number.isFinite(value.at);
}

function isEventTrace(value: unknown): boolean {
  return isRecord(value)
    && value.bounded === true
    && isPositiveInteger(value.max_events)
    && typeof value.truncated === "boolean";
}

function isCitation(value: unknown): boolean {
  return isRecord(value)
    && isText(value.source_id)
    && isText(value.filename)
    && isPositiveInteger(value.page)
    && isRecord(value.bbox)
    && [value.bbox.x0, value.bbox.top, value.bbox.x1, value.bbox.bottom]
      .every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate));
}

function isResultRow(value: unknown): boolean {
  return isRecord(value)
    && isText(value.row_id)
    && isNonNegativeInteger(value.index)
    && isCitation(value.citation);
}

function isTransactionLink(value: unknown): boolean {
  return isRecord(value)
    && isText(value.finding_id)
    && isText(value.link_id)
    && isText(value.newer_row_id)
    && isText(value.older_row_id)
    && (value.status === "PASS" || value.status === "FAIL")
    && [value.balance, value.signed_movement, value.derived_balance, value.comparison_balance, value.difference].every(isDecimalText)
    && isRecord(value.citations)
    && isCitation(value.citations.balance)
    && isCitation(value.citations.comparison_balance)
    && isReviewStatus(value.review_status);
}

function isResultCheck(value: unknown): boolean {
  return isRecord(value)
    && isText(value.finding_id)
    && isText(value.name)
    && typeof value.scope === "string"
    && isOutcome(value.status)
    && typeof value.detail === "string"
    && typeof value.evidence === "string"
    && isReviewStatus(value.review_status);
}

function isResultDocument(value: unknown): boolean {
  return isJobDocument(value)
    && isRecord(value)
    && (value.sha256 === undefined || isText(value.sha256))
    && (value.atlas === undefined || value.atlas === null || (isRecord(value.atlas)
      && (value.atlas.document_id === null || isText(value.atlas.document_id))))
    && (value.statement === undefined || isStatement(value.statement))
    && Array.isArray(value.rows)
    && value.rows.every(isResultRow)
    && Array.isArray(value.transaction_links)
    && value.transaction_links.every(isTransactionLink)
    && Array.isArray(value.checks)
    && value.checks.every(isResultCheck);
}

function isResultFinding(value: unknown): boolean {
  return isRecord(value)
    && isText(value.finding_id)
    && (value.kind === "CHECK" || value.kind === "TRANSACTION_LINK")
    && isText(value.source_id)
    && isOutcome(value.status)
    && isReviewStatus(value.review_status)
    && typeof value.title === "string"
    && typeof value.detail === "string";
}

function isDecimalText(value: unknown): boolean {
  return value === null || (typeof value === "string" && /^-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value));
}

function isStatement(value: unknown): boolean {
  return isRecord(value)
    && isText(value.account_short_code)
    && typeof value.account_name === "string"
    && typeof value.account_number === "string"
    && isText(value.currency)
    && typeof value.bank_name === "string"
    && typeof value.date_range === "string"
    && (value.closing_balance === undefined || isDecimalText(value.closing_balance))
    && isNonNegativeInteger(value.row_count);
}

function isResultArtifact(value: unknown): boolean {
  return isRecord(value)
    && isText(value.artifact_id)
    && value.kind === "RESULT_JSON"
    && isText(value.filename)
    && isText(value.content_type)
    && isText(value.url);
}

function isResultSummary(value: unknown): boolean {
  return isRecord(value)
    && isNonNegativeInteger(value.documents_total)
    && isNonNegativeInteger(value.documents_succeeded)
    && isNonNegativeInteger(value.documents_failed)
    && isRecord(value.checks)
    && [value.checks.PASS, value.checks.FAIL, value.checks.UNRESOLVED].every(isNonNegativeInteger)
    && isRecord(value.transaction_links)
    && [value.transaction_links.PASS, value.transaction_links.FAIL].every(isNonNegativeInteger);
}

function isReferenceValidation(value: unknown): boolean {
  return isRecord(value)
    && ["NOT_PROVIDED", "VALID", "INVALID"].includes(String(value.status))
    && Array.isArray(value.tables)
    && (value.error === undefined || typeof value.error === "string");
}

function isReplaySummary(value: unknown): boolean {
  return isRecord(value)
    && value.kind === "RECORDED_REPLAY"
    && isText(value.replay_id)
    && isText(value.original_batch_id)
    && isText(value.profile_id)
    && isStringArray(value.original_run_ids)
    && typeof value.recorded_seconds === "number"
    && Number.isFinite(value.recorded_seconds)
    && value.model_calls === 0
    && value.event_trace_available === false
    && hasLinks(value.links, ["self"]);
}

function isReplayAccount(value: unknown): boolean {
  return isRecord(value)
    && isText(value.account)
    && isText(value.run_id)
    && typeof value.accepted === "boolean"
    && isNonNegativeInteger(value.attempts)
    && typeof value.seconds === "number"
    && Number.isFinite(value.seconds)
    && isRecord(value.envelope);
}

async function responseError(response: Response): Promise<WorkspaceRequestError> {
  try {
    return requestErrorFromPayload(await response.json(), response.status);
  } catch {
    return new WorkspaceRequestError(`Request failed (${response.status}).`, response.status);
  }
}

function requestErrorFromPayload(payload: unknown, status: number): WorkspaceRequestError {
  const detail = isRecord(payload) ? payload.detail : undefined;
  const code = isRecord(detail) && typeof detail.code === "string" ? detail.code : undefined;
  return new WorkspaceRequestError(errorMessageFromPayload(payload, status), status, code);
}

function errorMessageFromPayload(payload: unknown, status: number): string {
  const fallback = `Request failed (${status}).`;
  if (!isRecord(payload)) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  if (isRecord(payload.detail) && typeof payload.detail.message === "string") {
    return typeof payload.detail.code === "string"
      ? `${payload.detail.code}: ${payload.detail.message}`
      : payload.detail.message;
  }
  if (Array.isArray(payload.detail)) {
    const details = payload.detail
      .map((item) => isRecord(item) && typeof item.msg === "string" ? item.msg : "")
      .filter(Boolean)
      .join(" ");
    if (details) return details;
  }
  if (typeof payload.message === "string") return payload.message;
  if (typeof payload.error === "string") return payload.error;
  return fallback;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "Unknown error");
}
