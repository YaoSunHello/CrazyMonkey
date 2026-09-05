import { describe, expect, it } from "vitest";
import { HttpReviewAdapter } from "./httpReviewAdapter";
import { MockReviewAdapter } from "./mockReviewAdapter";
import { createReviewAdapter } from "./reviewAdapter";

describe("review adapter configuration", () => {
  it("defaults to the explicitly labelled fixture adapter", () => {
    expect(createReviewAdapter()).toBeInstanceOf(MockReviewAdapter);
  });

  it("requires an explicit backend URL in live mode instead of falling back", () => {
    expect(() => createReviewAdapter("live", "  ")).toThrow(
      "VITE_API_BASE_URL is required when VITE_API_MODE=live. No fixture fallback was used.",
    );
  });

  it("creates the HTTP adapter only when live mode has a backend URL", () => {
    expect(createReviewAdapter("live", " https://review.example ")).toBeInstanceOf(HttpReviewAdapter);
  });
});
