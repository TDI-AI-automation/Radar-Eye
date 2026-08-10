import { useQuery } from "@tanstack/react-query";
import {
  getThreatAnalytics,
  getIncidentAnalytics,
  getCameraAnalytics,
  getSystemAnalytics,
} from "@/api/endpoints/analytics";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";

export function useThreatAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.threats(),
    queryFn: getThreatAnalytics,
    staleTime: STALE_TIME.analytics,
  });
}

export function useIncidentAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.incidents(),
    queryFn: getIncidentAnalytics,
    staleTime: STALE_TIME.analytics,
  });
}

export function useCameraAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.cameras(),
    queryFn: getCameraAnalytics,
    staleTime: STALE_TIME.analytics,
  });
}

export function useSystemAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.system(),
    queryFn: getSystemAnalytics,
    staleTime: STALE_TIME.analytics,
  });
}
