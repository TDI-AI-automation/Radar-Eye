/**
 * Centralized Query Key Factory.
 *
 * No query hook or component may hardcode a query key array literal --
 * every key used with TanStack Query comes from here. This is what makes
 * `queryClient.invalidateQueries()`/`setQueryData()` calls (from REST
 * mutations AND WebSocket handlers, per docs/FRONTEND_ARCHITECTURE.md's
 * "REST establishes baseline, WS carries incremental updates" rule) safe
 * to reason about: a key can only ever be constructed one way.
 *
 * One namespace per RM-12 REST domain (shared/schemas/*.py's grouping).
 * Each namespace's `all()` is the coarsest invalidation target for that
 * domain; everything else nests under it so `invalidateQueries({queryKey:
 * queryKeys.incidents.all()})` correctly invalidates every incidents query,
 * list or detail, without needing to enumerate them.
 */

export const queryKeys = {
  cameras: {
    all: () => ["cameras"] as const,
    list: () => [...queryKeys.cameras.all(), "list"] as const,
    detail: (cameraId: string) => [...queryKeys.cameras.all(), "detail", cameraId] as const,
    calibration: (cameraId: string) =>
      [...queryKeys.cameras.all(), "detail", cameraId, "calibration"] as const,
    health: (cameraId: string) =>
      [...queryKeys.cameras.all(), "detail", cameraId, "health"] as const,
  },

  threats: {
    all: () => ["threats"] as const,
    active: () => [...queryKeys.threats.all(), "active"] as const,
  },

  incidents: {
    all: () => ["incidents"] as const,
    list: () => [...queryKeys.incidents.all(), "list"] as const,
    open: () => [...queryKeys.incidents.all(), "open"] as const,
    detail: (incidentId: string) => [...queryKeys.incidents.all(), "detail", incidentId] as const,
    events: (incidentId: string) =>
      [...queryKeys.incidents.all(), "detail", incidentId, "events"] as const,
    evidence: (incidentId: string) =>
      [...queryKeys.incidents.all(), "detail", incidentId, "evidence"] as const,
  },

  reviews: {
    all: () => ["reviews"] as const,
    list: () => [...queryKeys.reviews.all(), "list"] as const,
    detail: (reviewId: string) => [...queryKeys.reviews.all(), "detail", reviewId] as const,
  },

  calibration: {
    all: () => ["calibration"] as const,
    cameras: () => [...queryKeys.calibration.all(), "cameras"] as const,
    results: () => [...queryKeys.calibration.all(), "results"] as const,
    forCamera: (cameraId: string) => [...queryKeys.calibration.all(), "camera", cameraId] as const,
  },

  evidence: {
    all: () => ["evidence"] as const,
    list: () => [...queryKeys.evidence.all(), "list"] as const,
    detail: (evidenceId: string) => [...queryKeys.evidence.all(), "detail", evidenceId] as const,
    recordings: () => [...queryKeys.evidence.all(), "recordings"] as const,
    recording: (recordingId: string) =>
      [...queryKeys.evidence.all(), "recordings", recordingId] as const,
    snapshot: (snapshotId: string) =>
      [...queryKeys.evidence.all(), "snapshots", snapshotId] as const,
  },

  analytics: {
    all: () => ["analytics"] as const,
    threats: () => [...queryKeys.analytics.all(), "threats"] as const,
    incidents: () => [...queryKeys.analytics.all(), "incidents"] as const,
    cameras: () => [...queryKeys.analytics.all(), "cameras"] as const,
    system: () => [...queryKeys.analytics.all(), "system"] as const,
  },

  users: {
    all: () => ["users"] as const,
    list: () => [...queryKeys.users.all(), "list"] as const,
  },

  health: {
    all: () => ["health"] as const,
    system: () => [...queryKeys.health.all(), "system"] as const,
    gpu: () => [...queryKeys.health.all(), "gpu"] as const,
    storage: () => [...queryKeys.health.all(), "storage"] as const,
    recording: () => [...queryKeys.health.all(), "recording"] as const,
    cameras: () => [...queryKeys.health.all(), "cameras"] as const,
  },
} as const;
