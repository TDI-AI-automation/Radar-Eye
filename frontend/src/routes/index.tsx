import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, StatTile } from "@/components/hud/Panel";
import { LiveCameraTile } from "@/components/shared/LiveCameraTile";
import { ThreatLevelBadge } from "@/components/shared/ThreatLevelBadge";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { useCameras, useCamerasHealth } from "@/queries/useCameras";
import { useActiveThreats } from "@/queries/useThreats";
import { useIncidents, useTransitionIncident } from "@/features/incidents/hooks/useIncidents";
import { useGpuHealth } from "@/features/health/hooks/useHealth";
import { usePermission } from "@/auth/usePermission";
import { Check, Radio } from "lucide-react";
import type { ThreatAssessment } from "@/domain/models/ThreatAssessment";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Live Monitoring — SENTINEL C2" },
      {
        name: "description",
        content: "Real-time AI-driven perimeter monitoring across all camera feeds.",
      },
      { property: "og:title", content: "Live Monitoring — SENTINEL C2" },
      {
        property: "og:description",
        content: "Real-time AI-driven perimeter monitoring across all camera feeds.",
      },
    ],
  }),
  component: LiveMonitoring,
});

/**
 * Final RM-13 migration phase, system-integration framing: this screen
 * exists to connect infrastructure already built (VideoProvider,
 * useCameras/useCamerasHealth, useActiveThreats, useIncidents,
 * useTransitionIncident -- all reused as-is, none rebuilt here) rather
 * than introduce anything new. The prototype's bounding-box detection
 * overlay and autoplay demo video are dropped, not replaced with a
 * fallback -- Phase 0 already flagged (§8) that no bounding-box
 * coordinates or live video delivery mechanism exist on the backend;
 * this is that flag finally being acted on, not a new finding. Threats
 * become a real chip list per camera and a dedicated panel instead.
 */
function LiveMonitoring() {
  const [emphasized, setEmphasized] = useState<string | null>(null);
  const canOperate = usePermission("operator");

  const camerasQuery = useCameras();
  const cameraHealthQuery = useCamerasHealth();
  const threatsQuery = useActiveThreats();
  const incidentsQuery = useIncidents();
  const gpuQuery = useGpuHealth();
  const transition = useTransitionIncident();

  const fpsByCameraId = useMemo(
    () => new Map((cameraHealthQuery.data ?? []).map((h) => [h.camera_id, h.fps])),
    [cameraHealthQuery.data],
  );

  const threatsByCameraId = useMemo(() => {
    const map = new Map<string, ThreatAssessment[]>();
    for (const t of threatsQuery.data ?? []) {
      const list = map.get(t.cameraId) ?? [];
      list.push(t);
      map.set(t.cameraId, list);
    }
    return map;
  }, [threatsQuery.data]);

  const cameras = useMemo(() => camerasQuery.data ?? [], [camerasQuery.data]);
  const cameraNameById = useMemo(() => new Map(cameras.map((c) => [c.id, c.name])), [cameras]);
  const criticalThreat = (threatsQuery.data ?? []).find((t) => t.requiresImmediateAction());
  const openIncidents = (incidentsQuery.data ?? []).filter((i) => !i.isTerminal());
  const onlineCount = cameras.filter((c) => c.isOnline()).length;

  return (
    <div className="p-3 space-y-3 min-h-full">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatTile label="Cameras" value={`${onlineCount}/${cameras.length}`} tone="cyan" />
        <StatTile
          label="Active Threats"
          value={(threatsQuery.data ?? []).length}
          tone={criticalThreat ? "red" : "cyan"}
        />
        <StatTile label="Open Incidents" value={openIncidents.length} tone="amber" />
        <StatTile
          label="GPU"
          value={
            gpuQuery.data?.utilization_percent != null
              ? `${gpuQuery.data.utilization_percent.toFixed(0)}%`
              : "—"
          }
          tone="cyan"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-3">
        <div className="space-y-3">
          {criticalThreat && (
            <div className="hud-panel hud-corner rounded flex items-center justify-between px-3 py-2 border-red-glow/60 animate-pulse-red">
              <div className="flex items-center gap-3">
                <ThreatLevelBadge level={criticalThreat.threatLevel} />
                <div>
                  <div className="font-mono text-xs text-glow-red uppercase tracking-widest">
                    Immediate action required
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono">
                    {cameraNameById.get(criticalThreat.cameraId) ?? criticalThreat.cameraId} · track{" "}
                    {criticalThreat.trackId}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setEmphasized(criticalThreat.cameraId)}
                className="rounded border border-primary/40 bg-primary/10 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20"
              >
                Focus
              </button>
            </div>
          )}

          {camerasQuery.isLoading ? (
            <LoadingState label="Loading cameras…" />
          ) : camerasQuery.isError ? (
            <ErrorState
              label="Failed to load cameras."
              onRetry={() => void camerasQuery.refetch()}
            />
          ) : cameras.length === 0 ? (
            <EmptyState label="No cameras registered." />
          ) : (
            <div
              className={`grid gap-3 ${emphasized ? "grid-cols-1 lg:grid-cols-[2fr_1fr]" : "grid-cols-1 md:grid-cols-2"}`}
            >
              {emphasized ? (
                <>
                  {(() => {
                    const cam = cameras.find((c) => c.id === emphasized) ?? cameras[0];
                    return (
                      <LiveCameraTile
                        camera={cam}
                        fps={fpsByCameraId.get(cam.id) ?? null}
                        threats={threatsByCameraId.get(cam.id) ?? []}
                        emphasized
                        onFullscreen={() => setEmphasized(null)}
                      />
                    );
                  })()}
                  <div className="grid grid-cols-1 gap-3">
                    {cameras
                      .filter((c) => c.id !== emphasized)
                      .map((c) => (
                        <LiveCameraTile
                          key={c.id}
                          camera={c}
                          fps={fpsByCameraId.get(c.id) ?? null}
                          threats={threatsByCameraId.get(c.id) ?? []}
                          onFullscreen={() => setEmphasized(c.id)}
                        />
                      ))}
                  </div>
                </>
              ) : (
                cameras.map((c) => (
                  <LiveCameraTile
                    key={c.id}
                    camera={c}
                    fps={fpsByCameraId.get(c.id) ?? null}
                    threats={threatsByCameraId.get(c.id) ?? []}
                    onFullscreen={() => setEmphasized(c.id)}
                  />
                ))
              )}
            </div>
          )}

          <Panel title={`Open Incidents · ${openIncidents.length}`}>
            {incidentsQuery.isLoading ? (
              <LoadingState label="Loading incidents…" />
            ) : incidentsQuery.isError ? (
              <ErrorState
                label="Failed to load incidents."
                onRetry={() => void incidentsQuery.refetch()}
              />
            ) : openIncidents.length === 0 ? (
              <EmptyState label="No open incidents." />
            ) : (
              <div className="max-h-72 overflow-auto divide-y divide-border/40">
                {openIncidents.map((i) => (
                  <div
                    key={i.id}
                    className="grid grid-cols-[auto_auto_1fr_auto] items-center gap-3 py-2 text-[11px] font-mono"
                  >
                    <ThreatLevelBadge level={i.threatLevel} />
                    <span className="text-primary">
                      {cameraNameById.get(i.cameraId) ?? i.cameraId}
                    </span>
                    <span className="text-foreground/90 truncate">{i.status}</span>
                    {i.canAcknowledge() ? (
                      <button
                        onClick={() =>
                          void transition.mutate({ incidentId: i.id, status: "ACKNOWLEDGED" })
                        }
                        disabled={!canOperate || transition.isPending}
                        title={!canOperate ? "Operator role required" : undefined}
                        className="inline-flex items-center gap-1 rounded border border-primary/40 px-1.5 py-0.5 text-primary hover:bg-primary/10 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Radio className="h-3 w-3" /> ACK
                      </button>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-success">
                        <Check className="h-3 w-3" /> {i.status}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-3">
          <Panel title={`Active Threats · ${(threatsQuery.data ?? []).length}`}>
            {threatsQuery.isLoading ? (
              <LoadingState />
            ) : threatsQuery.isError ? (
              <ErrorState onRetry={() => void threatsQuery.refetch()} />
            ) : (threatsQuery.data ?? []).length === 0 ? (
              <EmptyState label="No active threats." />
            ) : (
              <div className="space-y-2">
                {(threatsQuery.data ?? []).map((t) => (
                  <div
                    key={`${t.cameraId}-${t.trackId}`}
                    className="flex items-center justify-between font-mono text-[11px]"
                  >
                    <div>
                      <div className="text-primary">
                        {cameraNameById.get(t.cameraId) ?? t.cameraId}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        {t.weaponType} · {t.uniform} · {t.zone}
                      </div>
                    </div>
                    <ThreatLevelBadge level={t.threatLevel} />
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="GPU">
            {gpuQuery.isLoading ? (
              <LoadingState />
            ) : gpuQuery.data?.utilization_percent == null ? (
              <EmptyState label="GPU metrics unavailable in this environment." />
            ) : (
              <div className="font-mono text-[11px] space-y-1">
                <div className="text-glow-cyan text-2xl font-bold">
                  {gpuQuery.data.utilization_percent.toFixed(0)}%
                </div>
                {gpuQuery.data.temperature_celsius != null && (
                  <div className="text-muted-foreground">
                    {gpuQuery.data.temperature_celsius.toFixed(0)}°C
                  </div>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
