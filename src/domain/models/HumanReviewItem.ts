/**
 * HumanReviewItem domain model. Mirrors shared/schemas/review.py::
 * HumanReviewSchema exactly (GET /reviews, GET /reviews/{id}, and the
 * /ws/reviews creation-event body all use this one flat shape).
 *
 * CLAUDE.md's Human Review Rules: "Unknown uniforms must never be
 * auto-resolved... Operator action required." canResolve() is the single
 * fact backing all four resolution actions (confirm-military/confirm-
 * civilian/escalate/dismiss) -- apps/api/app/routers/reviews.py::_resolve()
 * rejects any resolution attempt once status != "OPEN", uniformly across
 * all four actions, so one fact covers all of them rather than four
 * separate (and here, identical) methods.
 */
export type ReviewStatus =
  | "OPEN"
  | "CONFIRMED_MILITARY"
  | "CONFIRMED_CIVILIAN"
  | "ESCALATED"
  | "DISMISSED";

export class HumanReviewItem {
  constructor(
    readonly id: string,
    readonly cameraId: string,
    readonly trackId: number,
    readonly reason: string,
    readonly status: ReviewStatus,
  ) {}

  canResolve(): boolean {
    return this.status === "OPEN";
  }

  isResolved(): boolean {
    return this.status !== "OPEN";
  }
}
