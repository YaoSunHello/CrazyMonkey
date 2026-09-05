import { HttpReviewAdapter } from "./httpReviewAdapter";
import { MockReviewAdapter } from "./mockReviewAdapter";
import type { ReviewAdapter } from "../types";

export function createReviewAdapter(apiMode?: string, configuredBaseUrl?: string): ReviewAdapter {
  const mode = apiMode ?? "mock";
  if (mode !== "mock" && mode !== "live") {
    throw new Error(`Unsupported VITE_API_MODE: ${mode}`);
  }
  if (mode === "mock") return new MockReviewAdapter();

  const baseUrl = configuredBaseUrl?.trim();
  if (!baseUrl) {
    throw new Error("VITE_API_BASE_URL is required when VITE_API_MODE=live. No fixture fallback was used.");
  }
  return new HttpReviewAdapter(baseUrl);
}

export const reviewAdapter = createReviewAdapter(
  import.meta.env.VITE_API_MODE,
  import.meta.env.VITE_API_BASE_URL,
);
