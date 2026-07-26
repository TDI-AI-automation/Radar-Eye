import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  listIncidents,
  listOpenIncidents,
  getIncident,
  getIncidentEvents,
  transitionIncident,
} from "@/api/endpoints/incidents";
import { toIncidentDomain, toIncidentSummaryDomain } from "@/domain/mappers/incidentMapper";
import type { IncidentStatus } from "@/domain/incidentStatus";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";
import { subscribeToChannel } from "@/ws/connection";
import type { IncidentMessage } from "@/ws/messages";

export function useIncidents() {
  useIncidentsChannel();

  return useQuery({
    queryKey: queryKeys.incidents.list(),
    queryFn: async () => {
      const dtos = (await listIncidents()) ?? [];
      return dtos.map(toIncidentSummaryDomain);
    },
    staleTime: STALE_TIME.liveFeed,
  });
}

export function useOpenIncidents() {
  return useQuery({
    queryKey: queryKeys.incidents.open(),
    queryFn: async () => {
      const dtos = (await listOpenIncidents()) ?? [];
      return dtos.map(toIncidentSummaryDomain);
    },
    staleTime: STALE_TIME.liveFeed,
  });
}

export function useIncident(incidentId: string | null) {
  return useQuery({
    queryKey: queryKeys.incidents.detail(incidentId ?? ""),
    queryFn: async () => {
      if (!incidentId) return null;
      const dto = await getIncident(incidentId);
      return dto ? toIncidentDomain(dto) : null;
    },
    enabled: incidentId !== null,
    staleTime: STALE_TIME.liveFeed,
  });
}

export function useIncidentEvents(incidentId: string | null) {
  return useQuery({
    queryKey: queryKeys.incidents.events(incidentId ?? ""),
    queryFn: async () => (incidentId ? ((await getIncidentEvents(incidentId)) ?? []) : []),
    enabled: incidentId !== null,
    staleTime: STALE_TIME.liveFeed,
  });
}

/**
 * /ws/incidents carries IncidentCreatedMessage | IncidentUpdatedMessage,
 * no discriminator on the wire (docs/FRONTEND_ARCHITECTURE.md §13),
 * distinguished via ws/messages.ts's isIncidentUpdatedMessage(). Neither
 * variant carries the full Incident shape (created: no timestamps/
 * incident_type; updated: no camera_id/track_id at all), so this always
 * invalidates rather than attempts a partial merge into the cached
 * Incident/IncidentSummary objects (§5's rule) -- both messages carry
 * incident_id, which is enough to target the specific detail query too.
 */
function useIncidentsChannel() {
  const queryClient = useQueryClient();

  useEffect(() => {
    return subscribeToChannel("incidents", (message) => {
      const incidentId = (message as IncidentMessage).incident_id;
      void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.open() });
      if (incidentId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.detail(incidentId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.events(incidentId) });
      }
    });
  }, [queryClient]);
}

/** PATCH /incidents/{id} -- operator-gated on the backend; callers must
 * also gate the UI affordance with usePermission("operator") AND the
 * relevant Incident.canAcknowledge()/.canClose() fact, per
 * docs/FRONTEND_ARCHITECTURE.md §12. */
export function useTransitionIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: { incidentId: string; status: IncidentStatus }) => {
      const dto = await transitionIncident(args.incidentId, { status: args.status });
      return dto ? toIncidentDomain(dto) : null;
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.incidents.open() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.incidents.detail(variables.incidentId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.incidents.events(variables.incidentId),
      });
    },
  });
}
