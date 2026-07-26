import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  listReviews,
  confirmMilitary,
  confirmCivilian,
  escalateReview,
  dismissReview,
} from "@/api/endpoints/reviews";
import { toHumanReviewItemDomain } from "@/domain/mappers/reviewMapper";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";
import { subscribeToChannel } from "@/ws/connection";

/**
 * /ws/reviews carries HumanReviewItemCreatedEvent only -- no resolution
 * event exists (docs/FRONTEND_ARCHITECTURE.md §11 Finding 1). The
 * documented mitigation is a short staleTime (STALE_TIME.reviews, 15s)
 * plus the QueryClient's global refetchOnWindowFocus, so a second
 * operator's view catches up quickly even without a push for resolutions;
 * WS invalidation below handles new items showing up promptly.
 */
export function useReviews() {
  useReviewsChannel();

  return useQuery({
    queryKey: queryKeys.reviews.list(),
    queryFn: async () => {
      const dtos = (await listReviews()) ?? [];
      return dtos.map(toHumanReviewItemDomain);
    },
    staleTime: STALE_TIME.reviews,
  });
}

function useReviewsChannel() {
  const queryClient = useQueryClient();

  useEffect(() => {
    return subscribeToChannel("reviews", () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviews.list() });
    });
  }, [queryClient]);
}

type ResolutionAction = "confirm-military" | "confirm-civilian" | "escalate" | "dismiss";

const RESOLVERS: Record<
  ResolutionAction,
  (reviewId: string) => ReturnType<typeof confirmMilitary>
> = {
  "confirm-military": confirmMilitary,
  "confirm-civilian": confirmCivilian,
  escalate: escalateReview,
  dismiss: dismissReview,
};

/** All four resolution actions -- operator-gated on the backend; callers
 * must also gate the UI affordance with usePermission("operator") AND
 * HumanReviewItem.canResolve(), per docs/FRONTEND_ARCHITECTURE.md §12. */
export function useResolveReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: { reviewId: string; action: ResolutionAction }) => {
      const dto = await RESOLVERS[args.action](args.reviewId);
      return dto ? toHumanReviewItemDomain(dto) : null;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviews.list() });
    },
  });
}
