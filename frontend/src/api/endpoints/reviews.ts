import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type HumanReviewDto = components["schemas"]["HumanReviewSchema"];

export function listReviews(): Promise<HumanReviewDto[] | null> {
  return apiClient.request<HumanReviewDto[]>("/reviews");
}

export function getReview(reviewId: string): Promise<HumanReviewDto | null> {
  return apiClient.request<HumanReviewDto>(`/reviews/${reviewId}`);
}

/** The four POST convenience routes -- operator-gated, no body (the route
 * itself fixes the target status). apps/api/app/routers/reviews.py: these
 * and the generic PATCH both funnel through the same _resolve(), which
 * rejects any resolution once status != "OPEN" -- matches
 * HumanReviewItem.canResolve(). Using the named routes here rather than
 * the generic PATCH -- self-documenting at the call site, one function
 * per real operator action. */
export function confirmMilitary(reviewId: string): Promise<HumanReviewDto | null> {
  return apiClient.request<HumanReviewDto>(`/reviews/${reviewId}/confirm-military`, {
    method: "POST",
  });
}

export function confirmCivilian(reviewId: string): Promise<HumanReviewDto | null> {
  return apiClient.request<HumanReviewDto>(`/reviews/${reviewId}/confirm-civilian`, {
    method: "POST",
  });
}

export function escalateReview(reviewId: string): Promise<HumanReviewDto | null> {
  return apiClient.request<HumanReviewDto>(`/reviews/${reviewId}/escalate`, { method: "POST" });
}

export function dismissReview(reviewId: string): Promise<HumanReviewDto | null> {
  return apiClient.request<HumanReviewDto>(`/reviews/${reviewId}/dismiss`, { method: "POST" });
}
