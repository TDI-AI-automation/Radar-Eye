import type { HumanReviewItem } from "@/domain/models/HumanReviewItem";

export interface ReviewRowViewModel {
  id: string;
  cameraId: string;
  cameraName: string;
  trackId: number;
  reason: string;
  status: HumanReviewItem["status"];
  canResolve: boolean;
  createdAt: Date;
}

/** HumanReviewSchema now carries created_at (previously absent -- the
 * queue used to be unsortable/unaged, tracked as a Phase 3 backend-gap;
 * fixed alongside ADR-029 Phase 5's classification wiring, since that's
 * what starts actually populating this queue from live detections). */
export function buildReviewRowViewModel(
  item: HumanReviewItem,
  cameraName: string | undefined,
): ReviewRowViewModel {
  return {
    id: item.id,
    cameraId: item.cameraId,
    cameraName: cameraName ?? item.cameraId,
    trackId: item.trackId,
    reason: item.reason,
    status: item.status,
    canResolve: item.canResolve(),
    createdAt: item.createdAt,
  };
}

/** Oldest-first -- an operator queue triages what's been waiting longest. */
export function sortReviewRowsByCreatedAt(rows: ReviewRowViewModel[]): ReviewRowViewModel[] {
  return [...rows].sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
}
