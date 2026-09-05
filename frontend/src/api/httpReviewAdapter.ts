import type {
  DetectedUpload,
  DocumentRole,
  EmailDraft,
  ExportFormat,
  ExportResult,
  HumanReviewUpdate,
  ReviewAdapter,
  ReviewFinding,
  ReviewProgress,
  ReviewResult,
  ReviewStart,
  TermCorrection,
} from "../types";
import { isCanonicalDecimalString } from "../utils/decimal";

export class HttpReviewAdapter implements ReviewAdapter {
  readonly mode = "live" as const;
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async detectDocuments(files: File[]): Promise<DetectedUpload[]> {
    const form = new FormData();
    const localFiles = files.map((file) => ({
      file,
      clientFileId: crypto.randomUUID(),
    }));
    localFiles.forEach(({ file, clientFileId }) => {
      form.append("files", file);
      form.append("client_file_ids", clientFileId);
    });
    const detected = await this.fetchJson<(Omit<DetectedUpload, "file"> & { clientFileId: string })[]>("/api/v1/documents/detect", {
      method: "POST",
      body: form,
    });
    const fileByClientId = new Map<string, File>(
      localFiles.map((item): [string, File] => [item.clientFileId, item.file]),
    );
    if (detected.length !== files.length || new Set(detected.map((item) => item.clientFileId)).size !== detected.length) {
      throw new Error("Document detection returned an inconsistent file manifest.");
    }
    return detected.map((document) => {
      const file = fileByClientId.get(document.clientFileId);
      if (!file) throw new Error("Document detection returned an unknown client file identifier.");
      return { ...document, file };
    });
  }

  async startReview(documents: DetectedUpload[]): Promise<ReviewStart> {
    const form = new FormData();
    form.append(
      "manifest",
      JSON.stringify(documents.map(({ file: _file, ...document }) => document)),
    );
    documents.forEach((document) => form.append("files", document.file));
    return this.fetchJson<ReviewStart>("/api/v1/reviews", { method: "POST", body: form });
  }

  async startSyntheticReview(): Promise<ReviewStart> {
    return this.fetchJson<ReviewStart>("/api/v1/demo/reviews", { method: "POST" });
  }

  async retryReview(reviewId: string): Promise<ReviewStart> {
    return this.fetchJson<ReviewStart>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/retry`,
      { method: "POST" },
    );
  }

  async getProgress(reviewId: string): Promise<ReviewProgress> {
    return this.fetchJson<ReviewProgress>(`/api/v1/reviews/${encodeURIComponent(reviewId)}/progress`);
  }

  async getReview(reviewId: string): Promise<ReviewResult> {
    const payload = await this.fetchJson<unknown>(`/api/v1/reviews/${encodeURIComponent(reviewId)}`);
    return requireReviewResult(payload);
  }

  async updateHumanReview(
    reviewId: string,
    findingId: string,
    update: HumanReviewUpdate,
  ): Promise<ReviewFinding> {
    return this.fetchJson<ReviewFinding>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/findings/${encodeURIComponent(findingId)}/review`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update) },
    );
  }

  async correctTerm(
    reviewId: string,
    findingId: string,
    correction: TermCorrection,
  ): Promise<ReviewFinding> {
    return this.fetchJson<ReviewFinding>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/findings/${encodeURIComponent(findingId)}/corrections`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(correction) },
    );
  }

  async uploadSupportingDocument(
    reviewId: string,
    file: File,
    role: DocumentRole,
  ): Promise<ReviewStart> {
    const form = new FormData();
    form.append("file", file);
    form.append("role", role);
    return this.fetchJson<ReviewStart>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/documents`,
      { method: "POST", body: form },
    );
  }

  async requestExport(reviewId: string, format: ExportFormat, version: number): Promise<ExportResult> {
    const response = await this.fetchResponse(
      `/api/runs/${encodeURIComponent(reviewId)}/versions/${version}/exports/${format}`,
    );
    if (response.status === 404 || response.status === 501) {
      return { available: false, message: `${format.toUpperCase()} output is not available.` };
    }
    if (!response.ok) throw new Error(await this.errorMessage(response));
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? `crazymonkey-review.${format}`;
    const versionHeader = response.headers.get("X-Review-Version");
    const reviewVersion = versionHeader ? Number(versionHeader) : undefined;
    return {
      available: true,
      filename,
      blob: await response.blob(),
      reviewVersion: Number.isFinite(reviewVersion) ? reviewVersion : undefined,
      snapshotSha256: response.headers.get("X-Snapshot-SHA256") ?? undefined,
    };
  }

  async prepareEmail(reviewId: string, version: number): Promise<EmailDraft> {
    const draft = await this.fetchJson<EmailDraft & {
      review_version?: number;
      snapshot_sha256?: string;
      send_instructions?: string;
    }>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/email/prepare?version=${version}`,
      { method: "POST" },
    );
    return {
      ...draft,
      reviewVersion: draft.reviewVersion ?? draft.review_version,
      snapshotSha256: draft.snapshotSha256 ?? draft.snapshot_sha256,
      sendInstructions: draft.sendInstructions ?? draft.send_instructions,
    };
  }

  async sendEmail(reviewId: string, draftId: string): Promise<{ sent: boolean; message: string }> {
    return this.fetchJson<{ sent: boolean; message: string }>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/email/send`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draftId, confirmed: true }),
      },
    );
  }

  private async fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchResponse(path, init);
    if (!response.ok) throw new Error(await this.errorMessage(response));
    return (await response.json()) as T;
  }

  private async fetchResponse(path: string, init?: RequestInit): Promise<Response> {
    try {
      const url = `${this.baseUrl}${path}`;
      return init === undefined ? await fetch(url) : await fetch(url, init);
    } catch (error) {
      const detail = error instanceof Error && error.message.trim()
        ? error.message.trim()
        : "The network request could not be completed.";
      throw new Error(`Backend unavailable. ${detail}`, { cause: error });
    }
  }

  private async errorMessage(response: Response): Promise<string> {
    const fallback = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { message?: string; error?: string; detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) {
        const details = body.detail.map((item) => item.msg).filter(Boolean).join(" ");
        if (details) return details;
      }
      return body.message ?? body.error ?? fallback;
    } catch {
      return fallback;
    }
  }
}

function requireReviewResult(payload: unknown): ReviewResult {
  if (!isReviewResult(payload)) {
    throw new Error(
      "The review service returned an incompatible BEACON presentation contract. No fixture fallback was used.",
    );
  }
  return payload;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const documentRoles = ["NAV_WORKBOOK", "LPA", "SIDE_LETTER", "INVESTOR_REGISTER", "SUPPORTING"] as const;
const recognitionStates = ["RECOGNISED", "NEEDS_CONFIRMATION", "MISSING"] as const;
const findingStatuses = ["MATCH", "DISCREPANCY", "CANNOT_VERIFY", "UNSUPPORTED"] as const;
const reviewStates = ["UNREVIEWED", "REVIEWED", "NEEDS_FOLLOW_UP", "TERM_CONFIRMED"] as const;
const severityStates = ["NONE", "INFO", "WARNING", "CRITICAL"] as const;
const confidenceStates = ["HIGH", "MEDIUM", "LOW", "NOT_SCORED"] as const;
const sourceKinds = ["PDF", "SPREADSHEET", "CSV", "TEXT"] as const;
const checkStates = ["COMPLETE", "CONCERN", "UNRESOLVED"] as const;
const reviewModes = ["SYNTHETIC_DEMO", "LIVE_OFFLINE", "LIVE_MODEL"] as const;
const reviewSources = ["ATLAS", "DEVELOPMENT_FIXTURE"] as const;

function isReviewResult(value: unknown): value is ReviewResult {
  if (!isRecord(value)) return false;
  return (
    isNonEmptyString(value.id) &&
    isPositiveInteger(value.version) &&
    isOneOf(value.mode, reviewModes) &&
    isOneOf(value.source, reviewSources) &&
    isOptionalString(value.sourceNotice) &&
    isNonEmptyString(value.fundName) &&
    isNonEmptyString(value.periodLabel) &&
    isNonEmptyString(value.createdAt) &&
    Array.isArray(value.documents) && value.documents.every(isReviewDocument) &&
    Array.isArray(value.findings) && value.findings.every(isReviewFinding) &&
    isOutputCapabilities(value.outputCapabilities)
  );
}

function isReviewDocument(value: unknown): boolean {
  return isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.filename) &&
    isOneOf(value.role, documentRoles) &&
    isOneOf(value.recognition, recognitionStates) &&
    (value.fileCount === undefined || isNonNegativeInteger(value.fileCount));
}

function isReviewFinding(value: unknown): boolean {
  return isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.investorId) &&
    isOptionalString(value.investorName) &&
    isNonEmptyString(value.checkName) &&
    isOptionalMoney(value.administratorValue) &&
    isOptionalMoney(value.expectedValue) &&
    isOptionalMoney(value.difference) &&
    isOneOf(value.status, findingStatuses) &&
    (value.severity === undefined || isOneOf(value.severity, severityStates)) &&
    isOptionalConfidence(value.confidence) &&
    isOneOf(value.humanReviewState, reviewStates) &&
    isNonEmptyString(value.explanation) &&
    isOptionalCalculation(value.calculation) &&
    Array.isArray(value.evidence) && value.evidence.every(isEvidenceReference) &&
    Array.isArray(value.checksPerformed) && value.checksPerformed.every(isObservableCheck) &&
    isOptionalString(value.challengerConcern) &&
    isOptionalString(value.verifierStatement) &&
    isOptionalRequiredAction(value.requiredAction) &&
    Array.isArray(value.notes) && value.notes.every(isReviewNote) &&
    Array.isArray(value.versions) && value.versions.length > 0 && value.versions.every(isFindingVersion);
}

function isOutputCapabilities(value: unknown): boolean {
  return isRecord(value) &&
    typeof value.pdf === "boolean" &&
    typeof value.excel === "boolean" &&
    typeof value.json === "boolean" &&
    typeof value.emailPrepare === "boolean" &&
    typeof value.emailSend === "boolean" &&
    (value.termCorrection === undefined || typeof value.termCorrection === "boolean");
}

function isOptionalMoney(value: unknown): boolean {
  return value === undefined || (
    isRecord(value) &&
    isExactDecimal(value.amount) &&
    isNonEmptyString(value.currency)
  );
}

function isOptionalCalculation(value: unknown): boolean {
  return value === undefined || (
    isRecord(value) &&
    Array.isArray(value.inputs) &&
    value.inputs.every((input) => isRecord(input) && isNonEmptyString(input.label) && typeof input.value === "string") &&
    isNonEmptyString(value.expression) &&
    value.result !== undefined && isOptionalMoney(value.result)
  );
}

function isEvidenceReference(value: unknown): boolean {
  return isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.documentId) &&
    isNonEmptyString(value.filename) &&
    isOneOf(value.documentRole, documentRoles) &&
    isOneOf(value.sourceKind, sourceKinds) &&
    isNonEmptyString(value.locator) &&
    isOptionalString(value.quote) &&
    isOptionalString(value.value) &&
    isOptionalString(value.context);
}

function isObservableCheck(value: unknown): boolean {
  return isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.label) &&
    isOneOf(value.state, checkStates);
}

function isReviewNote(value: unknown): boolean {
  return isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.author) &&
    isNonEmptyString(value.body) &&
    isNonEmptyString(value.createdAt);
}

function isFindingVersion(value: unknown): boolean {
  return isRecord(value) &&
    isPositiveInteger(value.version) &&
    isNonEmptyString(value.createdAt) &&
    isNonEmptyString(value.reason) &&
    (value.applicableRate === undefined || isExactDecimal(value.applicableRate)) &&
    isOptionalMoney(value.expectedValue);
}

function isOptionalConfidence(value: unknown): boolean {
  return value === undefined || (
    isRecord(value) &&
    isOneOf(value.label, confidenceStates) &&
    (value.score === undefined || (typeof value.score === "number" && Number.isFinite(value.score))) &&
    isNonEmptyString(value.basis)
  );
}

function isOptionalRequiredAction(value: unknown): boolean {
  return value === undefined || (
    isRecord(value) &&
    isNonEmptyString(value.label) &&
    (value.documentRole === undefined || isOneOf(value.documentRole, documentRoles))
  );
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || typeof value === "string";
}

function isExactDecimal(value: unknown): value is number | string {
  return (typeof value === "number" && Number.isFinite(value)) ||
    (typeof value === "string" && isCanonicalDecimalString(value));
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isOneOf(value: unknown, choices: readonly string[]): boolean {
  return typeof value === "string" && choices.includes(value);
}
