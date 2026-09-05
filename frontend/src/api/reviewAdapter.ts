import { HttpReviewAdapter } from "./httpReviewAdapter";
import { MockReviewAdapter } from "./mockReviewAdapter";
import type { ReviewAdapter } from "../types";

const apiMode = import.meta.env.VITE_API_MODE ?? "mock";

if (apiMode !== "mock" && apiMode !== "live") {
  throw new Error(`Unsupported VITE_API_MODE: ${apiMode}`);
}

export const reviewAdapter: ReviewAdapter =
  apiMode === "live"
    ? new HttpReviewAdapter(import.meta.env.VITE_API_BASE_URL ?? "")
    : new MockReviewAdapter();
