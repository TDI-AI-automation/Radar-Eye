import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { STALE_TIME } from "./queries/staleTimes";

export const getRouter = () => {
  // Global defaults are the most conservative tier (reference data);
  // individual query hooks (Phase 2/3) override staleTime per data class
  // via STALE_TIME, per docs/FRONTEND_ARCHITECTURE.md §7.
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME.reference,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
        retry: 1,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
