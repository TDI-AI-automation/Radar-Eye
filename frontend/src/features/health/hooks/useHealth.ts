import { useQuery } from "@tanstack/react-query";
import {
  getSystemHealth,
  getGpuHealth,
  getStorageHealth,
  getRecordingHealth,
} from "@/api/endpoints/health";
import { queryKeys } from "@/queries/queryKeys";

/**
 * Health metrics have no WS channel (docs/FRONTEND_ARCHITECTURE.md §11
 * Finding 2: /ws/camera-health carries discrete connection events, not
 * periodic GPU/CPU/storage telemetry) -- REST polling is a documented,
 * deliberate exception to "avoid polling where practical", not an
 * oversight. 15s matches STALE_TIME.liveFeed's order of magnitude for
 * comparable "how stale is acceptable" reasoning, kept local to this
 * feature rather than added to queries/staleTimes.ts since refetchInterval
 * (active polling) is a different mechanism than passive staleTime, used
 * only here.
 */
const HEALTH_POLL_INTERVAL_MS = 15_000;

export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.health.system(),
    queryFn: getSystemHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
  });
}

export function useGpuHealth() {
  return useQuery({
    queryKey: queryKeys.health.gpu(),
    queryFn: getGpuHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
  });
}

export function useStorageHealth() {
  return useQuery({
    queryKey: queryKeys.health.storage(),
    queryFn: getStorageHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
  });
}

export function useRecordingHealth() {
  return useQuery({
    queryKey: queryKeys.health.recording(),
    queryFn: getRecordingHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
  });
}
