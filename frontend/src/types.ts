export type DocumentRole =
  | "NAV_WORKBOOK"
  | "LPA"
  | "SIDE_LETTER"
  | "INVESTOR_REGISTER"
  | "SUPPORTING";

export type DocumentRecognition = "RECOGNISED" | "NEEDS_CONFIRMATION" | "MISSING";

export interface ReviewDocument {
  id: string;
  filename: string;
  role: DocumentRole;
  recognition: DocumentRecognition;
  fileCount?: number;
}

export interface DetectedUpload extends ReviewDocument {
  file: File;
}

export type ReviewStageCode =
  | "READING_FILES"
  | "EXTRACTING_TERMS"
  | "COMPARING_DOCUMENTS"
  | "CHALLENGING_ASSUMPTIONS"
  | "CHECKING_CALCULATIONS"
  | "PREPARING_REVIEW";

export type ReviewStageState = "PENDING" | "ACTIVE" | "COMPLETE" | "ERROR";

export interface ReviewStage {
  code: ReviewStageCode;
  label: string;
  state: ReviewStageState;
}

export interface ProgressMessage {
  id: string;
  text: string;
}

export interface ReviewProgress {
  reviewId: string;
  state: "QUEUED" | "PROCESSING" | "COMPLETE" | "FAILED";
  stages: ReviewStage[];
  messages: ProgressMessage[];
  error?: string;
}

export type FindingStatus = "MATCH" | "DISCREPANCY" | "CANNOT_VERIFY" | "UNSUPPORTED";
export type HumanReviewState =
  | "UNREVIEWED"
  | "REVIEWED"
  | "NEEDS_FOLLOW_UP"
  | "TERM_CONFIRMED";

export interface MoneyValue {
  amount: number;
  currency: string;
}

export interface CalculationInput {
  label: string;
  value: string;
}

export interface FindingCalculation {
  inputs: CalculationInput[];
  expression: string;
  result: MoneyValue;
}

export type EvidenceSourceKind = "PDF" | "SPREADSHEET" | "CSV" | "TEXT";

export interface EvidenceReference {
  id: string;
  documentId: string;
  filename: string;
  documentRole: DocumentRole;
  sourceKind: EvidenceSourceKind;
  locator: string;
  quote?: string;
  value?: string;
  context?: string;
}

export interface ObservableCheck {
  id: string;
  label: string;
  state: "COMPLETE" | "CONCERN" | "UNRESOLVED";
}

export interface ReviewNote {
  id: string;
  author: string;
  body: string;
  createdAt: string;
}

export interface FindingVersion {
  version: number;
  createdAt: string;
  reason: string;
  applicableRate?: number;
  expectedValue?: MoneyValue;
}

export interface RequiredAction {
  label: string;
  documentRole?: DocumentRole;
}

export interface ReviewFinding {
  id: string;
  investorId: string;
  checkName: string;
  administratorValue?: MoneyValue;
  expectedValue?: MoneyValue;
  difference?: MoneyValue;
  status: FindingStatus;
  humanReviewState: HumanReviewState;
  explanation: string;
  calculation?: FindingCalculation;
  evidence: EvidenceReference[];
  checksPerformed: ObservableCheck[];
  challengerConcern?: string;
  verifierStatement?: string;
  requiredAction?: RequiredAction;
  notes: ReviewNote[];
  versions: FindingVersion[];
}

export interface OutputCapabilities {
  pdf: boolean;
  excel: boolean;
  json: boolean;
  emailPrepare: boolean;
  emailSend: boolean;
  termCorrection?: boolean;
}

export interface ReviewResult {
  id: string;
  version: number;
  mode: "SYNTHETIC_DEMO" | "LIVE_OFFLINE" | "LIVE_MODEL";
  source: "ATLAS" | "DEVELOPMENT_FIXTURE";
  sourceNotice?: string;
  fundName: string;
  periodLabel: string;
  createdAt: string;
  documents: ReviewDocument[];
  findings: ReviewFinding[];
  outputCapabilities: OutputCapabilities;
}

export interface ReviewStart {
  reviewId: string;
}

export interface HumanReviewUpdate {
  state: HumanReviewState;
  note?: string;
  reviewerName: string;
}

export interface TermCorrection {
  annualRate: number;
  note: string;
  reviewerName: string;
}

export interface EmailDraft {
  id: string;
  status: "DRAFT";
  recipient: string;
  subject: string;
  body: string;
  attachments: string[];
}

export type ExportFormat = "pdf" | "excel" | "json";

export interface ExportResult {
  available: boolean;
  filename?: string;
  blob?: Blob;
  message?: string;
}

export interface ReviewAdapter {
  readonly mode: "mock" | "live";
  detectDocuments(files: File[]): Promise<DetectedUpload[]>;
  startReview(documents: DetectedUpload[]): Promise<ReviewStart>;
  startSyntheticReview(): Promise<ReviewStart>;
  retryReview(reviewId: string): Promise<ReviewStart>;
  getProgress(reviewId: string): Promise<ReviewProgress>;
  getReview(reviewId: string): Promise<ReviewResult>;
  updateHumanReview(
    reviewId: string,
    findingId: string,
    update: HumanReviewUpdate,
  ): Promise<ReviewFinding>;
  correctTerm(
    reviewId: string,
    findingId: string,
    correction: TermCorrection,
  ): Promise<ReviewFinding>;
  uploadSupportingDocument(reviewId: string, file: File, role: DocumentRole): Promise<ReviewStart>;
  requestExport(reviewId: string, format: ExportFormat, version: number): Promise<ExportResult>;
  prepareEmail(reviewId: string, version: number): Promise<EmailDraft>;
  sendEmail(reviewId: string, draftId: string): Promise<{ sent: boolean; message: string }>;
}
