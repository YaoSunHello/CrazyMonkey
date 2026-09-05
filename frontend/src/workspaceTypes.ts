export type ComputationalOutcome = "PASS" | "FAIL" | "UNRESOLVED";
export type HumanReviewStatus = "UNREVIEWED" | "REVIEWED" | "NEEDS_FOLLOW_UP";
export type JobProcessingState = "QUEUED" | "PROCESSING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
export type DocumentProcessingState = "PENDING" | "PROCESSING" | "SUCCEEDED" | "FAILED";

export interface BackendProfileSummary {
  id: string;
  label: string;
  description: string;
  documents: string;
  tables: string[];
  passes: string[];
  envelope: string[];
}

export interface CapabilityFormat {
  extension: string;
  content_types: string[];
}

export interface CapabilityProfile {
  profile_id: string;
  label: string;
  description: string;
  source: {
    purpose: "SOURCE";
    required: boolean;
    formats: CapabilityFormat[];
  };
  reference: {
    purpose: "REFERENCE";
    required: boolean;
    max_files: number;
    formats: CapabilityFormat[];
    tables: Array<{ name: string; sheet: string; columns: string[] }>;
  };
}

export interface BridgeCapabilities {
  api_version: "ui.v1";
  execution: {
    label: "LOCAL_DETERMINISTIC";
    model_calls: number;
    browser_commands_executed: boolean;
  };
  limits: {
    max_files: number;
    max_file_bytes: number;
    max_batch_bytes: number;
    max_path_depth: number;
    max_events_per_job: number;
  };
  profiles: CapabilityProfile[];
  artifacts: {
    json: { available: boolean; reason?: string };
    report: { available: boolean; reason?: string };
    workbook: { available: boolean; reason?: string };
  };
  review_statuses: HumanReviewStatus[];
}

export type BackendConnectionState = "CONNECTED" | "HEALTH_ONLY" | "UNAVAILABLE";

export interface BackendConnection {
  state: BackendConnectionState;
  label: string;
  detail: string;
}

export interface ReplaySummary {
  replay_id: string;
  kind: "RECORDED_REPLAY";
  original_batch_id: string;
  profile_id: string;
  original_run_ids: string[];
  recorded_seconds: number;
  model_calls: 0;
  event_trace_available: false;
  links: { self: string };
}

export interface ReplayList {
  replays: ReplaySummary[];
  note: string;
}

export interface RecordedReplay extends ReplaySummary {
  accounts: Array<{
    account: string;
    run_id: string;
    accepted: boolean;
    attempts: number;
    seconds: number;
    envelope: Record<string, unknown>;
  }>;
  timing: {
    mode: "RECORDED_SECONDS";
    compression_performed: false;
  };
  note: string;
}

export interface WorkspaceBootstrap {
  connection: BackendConnection;
  profiles: BackendProfileSummary[];
  capabilities?: BridgeCapabilities;
  replays: ReplaySummary[];
  issues: string[];
}

export type InventoryStatus =
  | "SUPPORTED"
  | "NEEDS_CONFIRMATION"
  | "EXCLUDED"
  | "UNSUPPORTED"
  | "UNREADABLE";
export type FilePurpose = "SOURCE" | "REFERENCE";

export interface DiscoveredFile {
  file?: File;
  relativePath: string;
  error?: string;
}

export interface InventoryEntry {
  clientFileId: string;
  file?: File;
  relativePath: string;
  filename: string;
  sizeBytes: number;
  contentType: string;
  status: InventoryStatus;
  reason: string;
  selected: boolean;
  purpose?: FilePurpose;
}

export interface StartJobRequest {
  profileId: string;
  caseName: string;
  entries: InventoryEntry[];
  idempotencyKey: string;
  onUploadProgress?: (progress: UploadProgress) => void;
}

export interface UploadProgress {
  loadedBytes: number;
  totalBytes: number;
  percentage: number;
}

export interface StartJobResponse {
  job_id: string;
  profile_id: string;
  case_name: string;
  execution_label: "LOCAL_DETERMINISTIC";
  processing_state: JobProcessingState;
  idempotency_reused: boolean;
  links: { status: string; result: string };
}

export interface JobDocumentStatus {
  source_id: string;
  client_file_id: string;
  relative_path: string;
  filename: string;
  purpose: FilePurpose;
  processing_state: DocumentProcessingState;
  computational_outcome: ComputationalOutcome | null;
  error?: string | null;
}

export interface JobEvent {
  kind: "think" | "tool" | "code" | "stdout" | "stderr" | "verdict" | "state" | "result";
  label: string;
  detail: string;
  status: "running" | "ok" | "fail" | "skip";
  body: string;
  meta: Record<string, unknown>;
  at: number;
}

export interface JobStatus {
  job_id: string;
  profile_id: string;
  case_name: string;
  execution_label: "LOCAL_DETERMINISTIC";
  processing_state: JobProcessingState;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  documents: JobDocumentStatus[];
  events: JobEvent[];
  event_trace: { bounded: true; max_events: number; truncated: boolean };
  links: { result: string };
}

export interface SourceCitation {
  source_id: string;
  filename: string;
  page: number;
  bbox: { x0: number; top: number; x1: number; bottom: number };
}

export interface ResultRow {
  row_id: string;
  index: number;
  bank_reference?: string;
  narrative?: string;
  value_date?: string;
  post_date?: string;
  credit?: string | null;
  debit?: string | null;
  balance?: string | null;
  citation: SourceCitation;
}

export interface TransactionLink {
  finding_id: string;
  link_id: string;
  newer_row_id: string;
  older_row_id: string;
  status: "PASS" | "FAIL";
  balance: string | null;
  signed_movement: string | null;
  derived_balance: string | null;
  comparison_balance: string | null;
  difference: string | null;
  citations: {
    balance: SourceCitation;
    comparison_balance: SourceCitation;
  };
  review_status: HumanReviewStatus;
}

export interface ResultCheck {
  finding_id: string;
  name: string;
  scope: string;
  status: ComputationalOutcome;
  detail: string;
  evidence: string;
  review_status: HumanReviewStatus;
}

export interface ResultDocument extends JobDocumentStatus {
  sha256?: string;
  atlas?: {
    document_id: string | null;
    document_hash?: string;
    extraction_status?: string;
    evidence_count?: number;
    warnings?: string[];
  } | null;
  statement?: {
    account_short_code: string;
    account_name: string;
    account_number: string;
    currency: string;
    bank_name: string;
    date_range: string;
    closing_balance?: string | null;
    row_count: number;
  };
  rows: ResultRow[];
  transaction_links: TransactionLink[];
  checks: ResultCheck[];
}

export interface ResultFinding {
  finding_id: string;
  kind: "CHECK" | "TRANSACTION_LINK";
  source_id: string;
  status: ComputationalOutcome;
  review_status: HumanReviewStatus;
  title: string;
  detail: string;
  evidence: unknown;
}

export interface ResultArtifact {
  artifact_id: string;
  kind: "RESULT_JSON";
  filename: string;
  content_type: string;
  url: string;
}

export interface JobResult {
  job_id: string;
  profile_id: string;
  case_name: string;
  execution_label: "LOCAL_DETERMINISTIC";
  processing_state: JobProcessingState;
  summary: {
    documents_total: number;
    documents_succeeded: number;
    documents_failed: number;
    checks: Record<ComputationalOutcome, number>;
    transaction_links: { PASS: number; FAIL: number };
  };
  reference_validation: {
    status: "NOT_PROVIDED" | "VALID" | "INVALID";
    source_id?: string;
    tables: Array<{ name: string; columns: string[]; row_count: number }>;
    error?: string;
  };
  agent_resolution: { status: "NOT_RUN"; reason: string };
  documents: ResultDocument[];
  findings: ResultFinding[];
  profile_projection: { status: "AVAILABLE" | "OMITTED"; reason?: string; data?: unknown };
  artifacts: ResultArtifact[];
  error?: string;
}

export interface FindingReviewResponse {
  job_id: string;
  finding_id: string;
  status: ComputationalOutcome;
  review_status: HumanReviewStatus;
  updated_at: string;
}

export interface WorkspaceAdapter {
  readonly sessionKey?: string;
  readonly mode: "live";
  bootstrap(): Promise<WorkspaceBootstrap>;
  startJob(request: StartJobRequest): Promise<StartJobResponse>;
  getJob(jobId: string): Promise<JobStatus>;
  getResult(jobId: string): Promise<JobResult>;
  updateFindingReview(
    jobId: string,
    findingId: string,
    reviewStatus: HumanReviewStatus,
  ): Promise<FindingReviewResponse>;
  getReplay(replayId: string): Promise<RecordedReplay>;
  sourceUrl(jobId: string, sourceId: string): string;
  artifactUrl(jobId: string, artifactId: string): string;
}
