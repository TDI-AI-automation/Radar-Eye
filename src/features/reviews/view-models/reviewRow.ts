import type { HumanReviewItem } from "@/domain/models/HumanReviewItem";

export interface ReviewRowViewModel {
  id: string;
  cameraId: string;
  cameraName: string;
  trackId: number;
  reason: string;
  status: HumanReviewItem["status"];
  canResolve: boolean;
}

/** HumanReviewSchema has no created_at/timestamp field at all (unlike
 * Incident/Camera/Recording) -- the queue cannot be sorted or aged
 * chronologically; this is a real backend-capability gap, not an
 * oversight here (tracked in the Phase 3 backend-gaps list). Rows are
 * shown in whatever order GET /reviews returns. */
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
  };
}
