import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { ThreatLevelBadge } from "@/components/shared/ThreatLevelBadge";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { MapPin, ChevronRight, PlayCircle } from "lucide-react";
import {
  useIncidents,
  useIncident,
  useIncidentEvents,
  useTransitionIncident,
} from "@/features/incidents/hooks/useIncidents";
import {
  buildIncidentRowViewModel,
  buildIncidentStatusCounts,
} from "@/features/incidents/view-models/incidentRow";
import { useCameras } from "@/queries/useCameras";
import { usePermission } from "@/auth/usePermission";
import { useVideoHandle } from "@/video/VideoProviderContext";

export const Route = createFileRoute("/incidents")({
  head: () => ({
    meta: [
      { title: "Incident Center — SENTINEL C2" },
      { name: "description", content: "Active and historical security incidents." },
      { property: "og:title", content: "Incident Center — SENTINEL C2" },
      { property: "og:description", content: "Active and historical security incidents." },
    ],
  }),
  component: Incidents,
});

/**
 * IncidentSummarySchema/IncidentSchema carry no weapon type, no assigned
 * operator, no confidence, no escalation field, no free-text location --
 * the prototype's "object"/"operator"/"confidence"/"escalation"/"location"
 * fields are dropped, not fabricated. "Resolved 24h"/"Avg. Response" had
 * no backing aggregate either (no time-windowed analytics endpoint
 * exists) -- replaced with real, all-time status counts. "Assign"/
 * "Export" actions have no backend support (Export is Evidence's job,
 * a separate future feature) and are replaced with real Acknowledge/
 * Resolve actions backed by PATCH /incidents/{id}, gated by both
 * Incident.canAcknowledge()/.canClose() (state fact) and
 * usePermission("operator") (authorization), per
 * docs/FRONTEND_ARCHITECTURE.md §12.
 */
function Incidents() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const incidentsQuery = useIncidents();
  const camerasQuery = useCameras();

  const cameraNameById = useMemo(
    () => new Map((camerasQuery.data ?? []).map((c) => [c.id, c.name])),
    [camerasQuery.data],
  );

  const rows = useMemo(
    () =>
      (incidentsQuery.data ?? []).map((i) =>
        buildIncidentRowViewModel(i, cameraNameById.get(i.cameraId)),
      ),
    [incidentsQuery.data, cameraNameById],
  );

  const counts = useMemo(
    () => buildIncidentStatusCounts(incidentsQuery.data ?? []),
    [incidentsQuery.data],
  );
  const effectiveSelectedId = selectedId ?? rows[0]?.id ?? null;

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-3">
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MiniStat label="Open" value={counts.open} tone="red" />
          <MiniStat label="Acknowledged" value={counts.acknowledged} tone="amber" />
          <MiniStat label="Resolved" value={counts.resolved} tone="success" />
          <MiniStat label="Total" value={rows.length} tone="cyan" />
        </div>

        <Panel title={`Incidents · ${rows.length}`}>
          {incidentsQuery.isLoading ? (
            <LoadingState label="Loading incidents…" />
          ) : incidentsQuery.isError ? (
            <ErrorState
              label="Failed to load incidents."
              onRetry={() => void incidentsQuery.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState label="No incidents recorded." />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {rows.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`text-left hud-panel rounded p-3 border transition ${
                    effectiveSelectedId === r.id
                      ? "border-primary/70 hud-panel-glow"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-mono text-[10px] tracking-widest text-muted-foreground">
                        {r.id}
                      </div>
                      <div className="mt-1 flex items-center gap-1 text-sm font-semibold">
                        <MapPin className="h-3 w-3 text-muted-foreground" /> {r.cameraName}
                      </div>
                    </div>
                    <ThreatLevelBadge level={r.threatLevel} />
                  </div>
                  <div className="mt-2 font-mono text-[10px] text-muted-foreground">{r.status}</div>
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {effectiveSelectedId && <IncidentDetail incidentId={effectiveSelectedId} />}
    </div>
  );
}

function IncidentDetail({ incidentId }: { incidentId: string }) {
  const incidentQuery = useIncident(incidentId);
  const eventsQuery = useIncidentEvents(incidentId);
  const transition = useTransitionIncident();
  const canOperate = usePermission("operator");
  const incident = incidentQuery.data;
  const videoHandle = useVideoHandle(incident?.cameraId ?? "");

  return (
    <Panel title={`${incidentId} · Detail`}>
      {incidentQuery.isLoading ? (
        <LoadingState />
      ) : incidentQuery.isError || !incident ? (
        <ErrorState label="Failed to load incident." onRetry={() => void incidentQuery.refetch()} />
      ) : (
        <div className="space-y-4">
          <div className="hud-panel rounded aspect-video bg-black relative overflow-hidden flex items-center justify-center">
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <PlayCircle className="h-8 w-8" />
              <span className="font-mono text-[10px] uppercase tracking-widest">
                {videoHandle.status === "unavailable" ? "No Signal" : videoHandle.status}
              </span>
            </div>
            <div className="absolute bottom-2 right-2">
              <ThreatLevelBadge level={incident.threatLevel} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <Field label="Track ID" value={String(incident.trackId)} />
            <Field label="Type" value={incident.incidentType} />
            <Field label="Status" value={incident.status} />
            <Field label="Threat Level" value={incident.threatLevel} />
            <Field label="Created" value={incident.createdAt.toLocaleString()} />
            <Field label="Updated" value={incident.updatedAt.toLocaleString()} />
          </div>

          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-primary mb-2">
              Event History
            </div>
            {eventsQuery.isLoading ? (
              <LoadingState label="Loading events…" />
            ) : (eventsQuery.data ?? []).length === 0 ? (
              <EmptyState label="No events recorded." />
            ) : (
              <ol className="space-y-2">
                {(eventsQuery.data ?? []).map((event) => (
                  <li
                    key={event.event_id}
                    className="flex items-center gap-3 font-mono text-[11px]"
                  >
                    <span className="text-muted-foreground w-32 shrink-0">
                      {new Date(event.created_at).toLocaleTimeString()}
                    </span>
                    <span className="flex-1">{event.event_type}</span>
                    <ChevronRight className="h-3 w-3 text-muted-foreground" />
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => void transition.mutate({ incidentId, status: "ACKNOWLEDGED" })}
              disabled={!canOperate || !incident.canAcknowledge() || transition.isPending}
              title={!canOperate ? "Operator role required" : undefined}
              className="rounded border border-primary/40 bg-primary/10 py-2 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Acknowledge
            </button>
            <button
              onClick={() => void transition.mutate({ incidentId, status: "RESOLVED" })}
              disabled={!canOperate || !incident.canClose() || transition.isPending}
              title={!canOperate ? "Operator role required" : undefined}
              className="rounded border border-border py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-primary disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Resolve
            </button>
          </div>
          {transition.isError && (
            <p className="text-glow-red font-mono text-[10px]" role="alert">
              Failed to update incident.
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "cyan" | "amber" | "red" | "success";
}) {
  const cls = {
    cyan: "text-glow-cyan",
    amber: "text-glow-amber",
    red: "text-glow-red",
    success: "text-success",
  }[tone];
  return (
    <div className="hud-panel rounded p-3">
      <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className={`font-mono text-2xl font-bold ${cls}`}>{value}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="hud-panel rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="text-foreground">{value}</div>
    </div>
  );
}
