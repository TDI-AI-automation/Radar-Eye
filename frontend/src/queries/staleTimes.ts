/**
 * Concrete numbers for docs/FRONTEND_ARCHITECTURE.md §7's "staleTime is
 * set per data class, not globally" rule. Query hooks (Phase 2/3) import
 * these instead of hardcoding a duration per hook, so the tiering policy
 * stays centrally adjustable, same reasoning as queryKeys.ts.
 */
export const STALE_TIME = {
  /** Threats, incidents, camera health -- WS carries incremental updates
   * into these caches (§5), so this is a safety net for missed events /
   * a stale read on first mount, not the primary freshness mechanism. */
  liveFeed: 30_000,
  /** Reviews specifically: §11 Finding 1 -- /ws/reviews has no resolution
   * event, so this tier also leans on refetchOnWindowFocus (set on the
   * QueryClient default) rather than WS alone. */
  reviews: 15_000,
  /** Cameras, users, calibration results -- changes on operator action,
   * not continuously. */
  reference: 5 * 60_000,
  /** Analytics aggregates -- reporting data, coarse by nature. */
  analytics: 10 * 60_000,
} as const;
