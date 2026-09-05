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

export class HttpReviewAdapter implements ReviewAdapter {
  readonly mode = "live" as const;

  constructor(private readonly baseUrl: string) {}

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
    return this.fetchJson<ReviewResult>(`/api/v1/reviews/${encodeURIComponent(reviewId)}`);
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
    const response = await fetch(
      `${this.baseUrl}/api/runs/${encodeURIComponent(reviewId)}/versions/${version}/exports/${format}`,
    );
    if (response.status === 404 || response.status === 501) {
      return { available: false, message: `${format.toUpperCase()} output is not available.` };
    }
    if (!response.ok) throw new Error(await this.errorMessage(response));
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? `crazymonkey-review.${format}`;
    return { available: true, filename, blob: await response.blob() };
  }

  async prepareEmail(reviewId: string, version: number): Promise<EmailDraft> {
    return this.fetchJson<EmailDraft>(
      `/api/v1/reviews/${encodeURIComponent(reviewId)}/email/prepare?version=${version}`,
      { method: "POST" },
    );
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
    const response = await fetch(`${this.baseUrl}${path}`, init);
    if (!response.ok) throw new Error(await this.errorMessage(response));
    return (await response.json()) as T;
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
