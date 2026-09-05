import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { App } from "./App";
import { MockReviewAdapter } from "./api/mockReviewAdapter";
import type { ReviewProgress } from "./types";

class ImmediateMockReviewAdapter extends MockReviewAdapter {
  override async getProgress(reviewId: string): Promise<ReviewProgress> {
    return { reviewId, state: "COMPLETE", stages: [], messages: [] };
  }
}

class FailingThenRetryAdapter extends MockReviewAdapter {
  private failed = false;

  override async getProgress(reviewId: string): Promise<ReviewProgress> {
    if (!this.failed) {
      this.failed = true;
      return {
        reviewId,
        state: "FAILED",
        stages: [],
        messages: [],
        error: "Atlas timed out while extracting terms.",
      };
    }
    return { reviewId, state: "COMPLETE", stages: [], messages: [] };
  }
}

describe("CrazyMonkey client-side resilience", () => {
  it("rejects unsupported, oversized and duplicate files before another detection request", async () => {
    const adapter = new MockReviewAdapter();
    const detectDocuments = vi.spyOn(adapter, "detectDocuments");
    render(<App adapter={adapter} />);
    const input = screen.getByLabelText("Select files") as HTMLInputElement;

    fireEvent.change(input, {
      target: { files: [new File(["not-supported"], "notes.docx")] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "notes.docx is not supported. Use XLSX, CSV or text PDF files.",
    );
    expect(detectDocuments).not.toHaveBeenCalled();

    const oversized = new File(["small-test-body"], "oversized.pdf", { type: "application/pdf" });
    Object.defineProperty(oversized, "size", { value: 25 * 1024 * 1024 + 1 });
    fireEvent.change(input, { target: { files: [oversized] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "oversized.pdf exceeds the 25 MB per-file limit.",
    );
    expect(detectDocuments).not.toHaveBeenCalled();

    const valid = new File(["pdf"], "fund_LPA.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [valid] } });
    expect(await screen.findByText("fund_LPA.pdf")).toBeInTheDocument();
    expect(detectDocuments).toHaveBeenCalledTimes(1);

    fireEvent.change(input, {
      target: { files: [new File(["pdf"], "fund_LPA.pdf", { type: "application/pdf" })] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("fund_LPA.pdf has already been added.");
    expect(detectDocuments).toHaveBeenCalledTimes(1);
  });

  it("surfaces processing failure and invokes retryReview before completing", async () => {
    const user = userEvent.setup();
    const adapter = new FailingThenRetryAdapter();
    const retryReview = vi.spyOn(adapter, "retryReview");
    render(<App adapter={adapter} />);

    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));

    expect(await screen.findByRole("heading", { name: "The review could not continue" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Atlas timed out while extracting terms.");

    await user.click(screen.getByRole("button", { name: "Retry review" }));

    expect(retryReview).toHaveBeenCalledTimes(1);
    expect(retryReview).toHaveBeenCalledWith("review-demo-q3-2026");
    expect(await screen.findByRole("heading", { name: "Review summary" })).toBeInTheDocument();
  });

  it("keeps unavailable exports disabled and email in an unsent preview state", async () => {
    const user = userEvent.setup();
    const adapter = new ImmediateMockReviewAdapter();
    const sendEmail = vi.spyOn(adapter, "sendEmail");
    render(<App adapter={adapter} />);

    await user.click(screen.getByRole("button", { name: "Load synthetic demo" }));
    expect(await screen.findByRole("heading", { name: "Review summary" })).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "PDF report" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Excel review" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "JSON audit package" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Prepare email" }));

    expect(await screen.findByRole("dialog", { name: "Email preview" })).toBeInTheDocument();
    expect(screen.getByText("Draft — not sent")).toBeInTheDocument();
    expect(screen.getByText("Sending is unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm and send" })).toBeDisabled();
    await waitFor(() => expect(sendEmail).not.toHaveBeenCalled());
  });
});
