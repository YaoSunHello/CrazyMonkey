import { syntheticReviewFixture } from "../data/syntheticReview";
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

const progressLabels = [
  ["READING_FILES", "Reading files"],
  ["EXTRACTING_TERMS", "Extracting investor terms"],
  ["COMPARING_DOCUMENTS", "Comparing governing documents"],
  ["CHALLENGING_ASSUMPTIONS", "Challenging assumptions"],
  ["CHECKING_CALCULATIONS", "Checking calculations"],
  ["PREPARING_REVIEW", "Preparing review"],
] as const;

const progressMessages = [
  "Reading 8 supplied files",
  "6 investors identified",
  "5 side letters matched",
  "1 expected document missing",
  "Recalculating management fees",
  "Review findings prepared",
];

function cloneFixture(): ReviewResult {
  return structuredClone(syntheticReviewFixture);
}

function guessRole(file: File): { role: DocumentRole; recognised: boolean } {
  const name = file.name.toLowerCase();
  const isDataFile = /\.(xlsx|csv)$/i.test(name);
  if (isDataFile && (/\bnav\b/i.test(name) || /administrator/i.test(name))) {
    return { role: "NAV_WORKBOOK", recognised: true };
  }
  if (/\.pdf$/i.test(name) && /(^|[^a-z0-9])lpa([^a-z0-9]|$)|partnership.agreement/i.test(name)) {
    return { role: "LPA", recognised: true };
  }
  if (/side.?letter/i.test(name)) {
    return { role: "SIDE_LETTER", recognised: true };
  }
  if (/investor|register|input/i.test(name) && isDataFile) {
    return { role: "INVESTOR_REGISTER", recognised: true };
  }
  return { role: "SUPPORTING", recognised: false };
}

function parseMoneyLabel(value: string): number {
  return Number(value.replace(/[^0-9.-]+/g, ""));
}

export class MockReviewAdapter implements ReviewAdapter {
  readonly mode = "mock" as const;
  private readonly reviews = new Map<string, ReviewResult>();
  private readonly pollCounts = new Map<string, number>();

  async detectDocuments(files: File[]): Promise<DetectedUpload[]> {
    return files.map((file, index) => {
      const guessed = guessRole(file);
      return {
        id: `upload-${Date.now()}-${index}`,
        filename: file.name,
        role: guessed.role,
        recognition: guessed.recognised ? "RECOGNISED" : "NEEDS_CONFIRMATION",
        file,
      };
    });
  }

  async startReview(documents: DetectedUpload[]): Promise<ReviewStart> {
    void documents;
    throw new Error(
      "Uploaded-pack review requires the Atlas service. Development fixture mode will not invent findings for selected files.",
    );
  }

  async startSyntheticReview(): Promise<ReviewStart> {
    const review = cloneFixture();
    this.reviews.set(review.id, review);
    this.pollCounts.set(review.id, 0);
    return { reviewId: review.id };
  }

  async retryReview(reviewId: string): Promise<ReviewStart> {
    this.requireReview(reviewId);
    this.pollCounts.set(reviewId, 0);
    return { reviewId };
  }

  async getProgress(reviewId: string): Promise<ReviewProgress> {
    this.requireReview(reviewId);
    const previousCount = this.pollCounts.get(reviewId) ?? 0;
    const completedCount = Math.min(previousCount, progressLabels.length);
    this.pollCounts.set(reviewId, previousCount + 1);

    return {
      reviewId,
      state: completedCount === progressLabels.length ? "COMPLETE" : "PROCESSING",
      stages: progressLabels.map(([code, label], index) => ({
        code,
        label,
        state:
          index < completedCount ? "COMPLETE" : index === completedCount ? "ACTIVE" : "PENDING",
      })),
      messages: progressMessages
        .slice(0, Math.min(completedCount + 1, progressMessages.length))
        .map((message, index) => ({ id: `message-${index}`, text: message })),
    };
  }

  async getReview(reviewId: string): Promise<ReviewResult> {
    return structuredClone(this.requireReview(reviewId));
  }

  async updateHumanReview(
    reviewId: string,
    findingId: string,
    update: HumanReviewUpdate,
  ): Promise<ReviewFinding> {
    const finding = this.requireFinding(reviewId, findingId);
    finding.humanReviewState = update.state;
    if (update.note?.trim()) {
      finding.notes.push({
        id: `note-${Date.now()}`,
        author: update.reviewerName || "Reviewer",
        body: update.note.trim(),
        createdAt: new Date().toISOString(),
      });
    }
    return structuredClone(finding);
  }

  async correctTerm(
    reviewId: string,
    findingId: string,
    correction: TermCorrection,
  ): Promise<ReviewFinding> {
    const finding = this.requireFinding(reviewId, findingId);
    if (!finding.calculation || !finding.administratorValue) {
      throw new Error("This finding does not contain a recalculable term.");
    }

    const feeBaseInput = finding.calculation.inputs.find((input) => input.label === "Fee base");
    if (!feeBaseInput) throw new Error("The fee base is unavailable.");
    const feeBase = parseMoneyLabel(feeBaseInput.value);
    const expectedAmount = feeBase * (correction.annualRate / 100) * 0.25;
    const difference = Math.abs(finding.administratorValue.amount - expectedAmount);
    const nextVersion = Math.max(...finding.versions.map((version) => version.version)) + 1;

    finding.expectedValue = { amount: expectedAmount, currency: finding.administratorValue.currency };
    finding.difference = { amount: difference, currency: finding.administratorValue.currency };
    finding.status = difference < 0.005 ? "MATCH" : "DISCREPANCY";
    finding.humanReviewState = "UNREVIEWED";
    finding.calculation.inputs = finding.calculation.inputs.map((input) =>
      input.label === "Applicable annual fee" ? { ...input, value: `${correction.annualRate}%` } : input,
    );
    finding.calculation.expression = `${feeBaseInput.value} × ${correction.annualRate}% × 0.25`;
    finding.calculation.result = { amount: expectedAmount, currency: finding.administratorValue.currency };
    finding.explanation =
      `The extracted annual rate was corrected to ${correction.annualRate}% by ${correction.reviewerName || "the reviewer"}. ` +
      "This development fixture recalculated the numerical comparison and created a new version.";
    finding.challengerConcern =
      difference < 0.005
        ? undefined
        : "The recalculated expected amount still differs from the administrator value.";
    finding.verifierStatement =
      `Fixture recalculation confirms an expected fee of ${new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: finding.administratorValue.currency,
        minimumFractionDigits: 2,
      }).format(expectedAmount)} using the corrected rate.`;
    finding.checksPerformed = finding.checksPerformed.map((check) => {
      if (check.id === "recompute") {
        return { ...check, label: "Fee calculation recomputed using the corrected term", state: "COMPLETE" };
      }
      if (check.id === "compare") {
        return {
          ...check,
          label: "Administrator value compared with the corrected result",
          state: difference < 0.005 ? "COMPLETE" : "CONCERN",
        };
      }
      return check;
    });
    finding.versions.push({
      version: nextVersion,
      createdAt: new Date().toISOString(),
      reason: correction.note,
      applicableRate: correction.annualRate,
      expectedValue: structuredClone(finding.expectedValue),
    });
    finding.notes.push({
      id: `note-${Date.now()}`,
      author: correction.reviewerName || "Reviewer",
      body: `Corrected extracted annual fee to ${correction.annualRate}%. ${correction.note}`,
      createdAt: new Date().toISOString(),
    });
    return structuredClone(finding);
  }

  async uploadSupportingDocument(
    reviewId: string,
    file: File,
    role: DocumentRole,
  ): Promise<ReviewStart> {
    const review = this.requireReview(reviewId);
    review.documents.push({
      id: `supplement-${Date.now()}`,
      filename: file.name,
      role,
      recognition: "RECOGNISED",
    });
    review.sourceNotice =
      "Development UI fixture — the supporting file was recorded but not parsed because Atlas is not connected.";
    this.pollCounts.set(reviewId, 0);
    return { reviewId };
  }

  async requestExport(reviewId: string, format: ExportFormat, version: number): Promise<ExportResult> {
    const review = this.requireReview(reviewId);
    if (version !== review.version) {
      throw new Error("The requested development fixture version is unavailable.");
    }
    if (format !== "json") {
      return {
        available: false,
        message: `${format === "pdf" ? "PDF" : "Excel"} output is awaiting the Relay endpoint.`,
      };
    }
    const contents = JSON.stringify(review, null, 2);
    return {
      available: true,
      filename: `crazymonkey-${review.id}-development-fixture.json`,
      blob: new Blob([contents], { type: "application/json" }),
    };
  }

  async prepareEmail(reviewId: string, version: number): Promise<EmailDraft> {
    const review = this.requireReview(reviewId);
    if (version !== review.version) {
      throw new Error("The requested development fixture version is unavailable.");
    }
    const discrepancies = review.findings.filter((finding) => finding.status === "DISCREPANCY").length;
    const cannotVerify = review.findings.filter((finding) => finding.status === "CANNOT_VERIFY").length;
    return {
      id: `draft-${review.id}`,
      status: "DRAFT",
      recipient: "fund-operations@example.com",
      subject: `${review.periodLabel} — items requiring review`,
      body: [
        "Hello,",
        "",
        `CrazyMonkey's development fixture contains ${discrepancies} discrepancies and ${cannotVerify} item that could not be verified.`,
        "Please review the attached output when the Relay service is connected.",
        "",
        "Regards,",
        "NAV Review Team",
      ].join("\n"),
      attachments: ["PDF report (awaiting Relay)", "Excel review (awaiting Relay)"],
    };
  }

  async sendEmail(_reviewId: string, _draftId: string): Promise<{ sent: boolean; message: string }> {
    return {
      sent: false,
      message: "Email was not sent. The Relay send endpoint is not connected in development fixture mode.",
    };
  }

  private requireReview(reviewId: string): ReviewResult {
    const review = this.reviews.get(reviewId);
    if (!review) throw new Error(`Review ${reviewId} was not found.`);
    return review;
  }

  private requireFinding(reviewId: string, findingId: string): ReviewFinding {
    const finding = this.requireReview(reviewId).findings.find((candidate) => candidate.id === findingId);
    if (!finding) throw new Error(`Finding ${findingId} was not found.`);
    return finding;
  }
}
