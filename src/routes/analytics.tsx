import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { Panel, Bar } from "@/components/hud/Panel";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import {
  useThreatAnalytics,
  useIncidentAnalytics,
  useCameraAnalytics,
  useSystemAnalytics,
} from "@/features/analytics/hooks/useAnalytics";
import {
  buildThreatLevelCounts,
  buildIncidentStatusCounts,
  buildTopCamerasByIncidents,
} from "@/features/analytics/view-models/analyticsViewModels";
import { useCameras } from "@/queries/useCameras";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [
      { title: "AI Analytics — SENTINEL C2" },
      { name: "description", content: "Detection and incident analytics across the deployment." },
      { property: "og:title", content: "AI Analytics — SENTINEL C2" },
      {
        property: "og:description",
        content: "Detection and incident analytics across the deployment.",
      },
    ],
  }),
  component: Analytics,
});

/**
 * RM-12's /analytics/* endpoints are coarse repository-query aggregations
 * (shared/schemas/analytics.py's own docstring), not a computation engine
 * -- no time-windowed trends, no precision/recall/response-time metrics,
 * no per-sector heatmap, no weapon-frequency breakdown. The prototype's
 * Analytics screen assumed all of those; this migration keeps only what
 * the backend actually provides, per RM-13's "backend wins" rule.
 * GPU/inference metrics moved to System Health, where the real
 * /health/gpu endpoint actually lives.
 */
function Analytics() {
  const threatQuery = useThreatAnalytics();
  const incidentQuery = useIncidentAnalytics();
  const cameraQuery = useCameraAnalytics();
  const systemQuery = useSystemAnalytics();
  const camerasQuery = useCameras();

  const threatCounts = useMemo(() => buildThreatLevelCounts(threatQuery.data), [threatQuery.data]);
  const statusCounts = useMemo(
    () => buildIncidentStatusCounts(incidentQuery.data),
    [incidentQuery.data],
  );
  const topCameras = useMemo(
    () => buildTopCamerasByIncidents(cameraQuery.data),
    [cameraQuery.data],
  );
  const cameraNameById = useMemo(
    () => new Map((camerasQuery.data ?? []).map((c) => [c.id, c.name])),
    [camerasQuery.data],
  );

  const maxThreatCount = Math.max(1, ...threatCounts.map((r) => r.count));
  const maxTopCameraCount = Math.max(1, ...topCameras.map((r) => r.incidentCount));

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
      <Panel title="Threats by Level">
        {threatQuery.isLoading ? (
          <LoadingState />
        ) : threatQuery.isError ? (
          <ErrorState onRetry={() => void threatQuery.refetch()} />
        ) : threatCounts.every((r) => r.count === 0) ? (
          <EmptyState label="No threat assessments recorded yet." />
        ) : (
          threatCounts.map((r) => (
            <div
              key={r.level}
              className="flex items-center justify-between font-mono text-[11px] py-1"
            >
              <span style={{ color: r.color }}>{r.label}</span>
              <div className="flex-1 mx-3">
                <Bar value={(r.count / maxThreatCount) * 100} tone="cyan" />
              </div>
              <span className="text-muted-foreground w-8 text-right">{r.count}</span>
            </div>
          ))
        )}
      </Panel>

      <Panel title="Incidents">
        {incidentQuery.isLoading ? (
          <LoadingState />
        ) : incidentQuery.isError ? (
          <ErrorState onRetry={() => void incidentQuery.refetch()} />
        ) : (
          <>
            <div className="mb-3">
              <div className="font-mono text-3xl font-bold text-glow-cyan">
                {incidentQuery.data?.total ?? 0}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-widest">
                Total incidents
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
              {statusCounts.map((r) => (
                <div key={r.status} className="hud-panel rounded p-2">
                  <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
                    {r.status}
                  </div>
                  <div className="text-glow-cyan">{r.count}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <Panel title="Top Cameras by Incidents">
        {cameraQuery.isLoading ? (
          <LoadingState />
        ) : cameraQuery.isError ? (
          <ErrorState onRetry={() => void cameraQuery.refetch()} />
        ) : topCameras.length === 0 ? (
          <EmptyState label="No incidents recorded yet." />
        ) : (
          topCameras.map((r) => (
            <div
              key={r.cameraId}
              className="flex items-center justify-between font-mono text-[11px] py-1"
            >
              <span className="text-primary">{cameraNameById.get(r.cameraId) ?? r.cameraId}</span>
              <div className="flex-1 mx-3">
                <Bar value={(r.incidentCount / maxTopCameraCount) * 100} tone="cyan" />
              </div>
              <span className="text-muted-foreground w-8 text-right">{r.incidentCount}</span>
            </div>
          ))
        )}
      </Panel>

      <Panel title="System Totals">
        {systemQuery.isLoading ? (
          <LoadingState />
        ) : systemQuery.isError ? (
          <ErrorState onRetry={() => void systemQuery.refetch()} />
        ) : (
          <div className="grid grid-cols-2 gap-3 font-mono text-[11px]">
            <MiniKV k="Cameras" v={systemQuery.data?.total_cameras ?? 0} />
            <MiniKV k="Incidents" v={systemQuery.data?.total_incidents ?? 0} />
            <MiniKV k="Reviews" v={systemQuery.data?.total_reviews ?? 0} />
            <MiniKV k="Audit Entries" v={systemQuery.data?.total_audit_entries ?? 0} />
          </div>
        )}
      </Panel>
    </div>
  );
}

function MiniKV({ k, v }: { k: string; v: number }) {
  return (
    <div className="hud-panel rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted-foreground">{k}</div>
      <div className="text-glow-cyan">{v}</div>
    </div>
  );
}
