import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { listActiveThreats } from "@/api/endpoints/threats";
import { toThreatAssessmentDomain } from "@/domain/mappers/threatMapper";
import { queryKeys } from "./queryKeys";
import { STALE_TIME } from "./staleTimes";
import { subscribeToChannel } from "@/ws/connection";

/**
 * Shared (queries/, not features/) like useCameras() -- both Live
 * Monitoring and Tactical Map need "current active threats." /ws/threats
 * carries the full ThreatAssessment shape (ActiveThreatSchema "extends...
 * with no additional fields"), so a merge would be technically safe, but
 * this stays consistent with every other WS-consuming query in this
 * codebase (invalidate, not merge) per the Phase 3 review's explicit
 * "correctness over micro-optimization" endorsement -- one exception here
 * would make the rule inconsistent for no strong reason.
 */
export function useActiveThreats() {
  useThreatsChannel();

  return useQuery({
    queryKey: queryKeys.threats.active(),
    queryFn: async () => {
      const dtos = (await listActiveThreats()) ?? [];
      return dtos.map(toThreatAssessmentDomain);
    },
    staleTime: STALE_TIME.liveFeed,
  });
}

function useThreatsChannel() {
  const queryClient = useQueryClient();

  useEffect(() => {
    return subscribeToChannel("threats", () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.threats.active() });
    });
  }, [queryClient]);
}
