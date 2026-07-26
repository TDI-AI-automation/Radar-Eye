import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { ThreatLevelBadge } from "@/components/shared/ThreatLevelBadge";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { MapPinOff, Camera as CameraIcon } from "lucide-react";
import { useCameras, useCamerasHealth } from "@/queries/useCameras";
import { useActiveThreats } from "@/queries/useThreats";
import type { Camera } from "@/domain/models/Camera";

export const Route = createFileRoute("/map")({
  head: () => ({
    meta: [
      { title: "Tactical Map — SENTINEL C2" },
      { name: "description", content: "Perimeter camera status and active threats." },
      { property: "og:title", content: "Tactical Map — SENTINEL C2" },
      { property: "og:description", content: "Perimeter camera status and active threats." },
    ],
  }),
  component: TacticalMap,
});

/**
 * The prototype's map was entirely coordinate-driven (x/y percent
 * positions, rotation/FOV cones, patrol routes, blind-spot polygons) --
 * none of it has a backend source. CameraSchema.location is free text
 * ("North Gate · Sector A"), never lat/lng or any grid coordinate (§10/§11
 * flagged this since Phase 0; §16 tracks it as a backend gap). Per the
 * final-phase review's explicit instruction -- "do not implement
 * synthetic map intelligence... represent only what is actually known" --
 * this is an honest operational status board grouped by the real
 * location text, not a fake positioned map. If camera geo-coordinates are
 * ever added to the backend, a real spatial view can replace this without
 * touching any other screen (same domain models/queries feed both).
 */
function TacticalMap() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const camerasQuery = useCameras();
  const healthQuery = useCamerasHealth();
  const threatsQuery = useActiveThreats();

  const fpsByCameraId = useMemo(
    () => new Map((healthQuery.data ?? []).map((h) => [h.camera_id, h.fps])),
    [healthQuery.data],
  );

  const threatCountByCameraId = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of threatsQuery.data ?? []) {
      map.set(t.cameraId, (map.get(t.cameraId) ?? 0) + 1);
    }
    return map;
  }, [threatsQuery.data]);

  const cameras = useMemo(() => camerasQuery.data ?? [], [camerasQuery.data]);
  const groups = useMemo(() => groupByLocation(cameras), [cameras]);
  const selected = cameras.find((c) => c.id === selectedId) ?? null;
  const selectedThreats = (threatsQuery.data ?? []).filter((t) => t.cameraId === selectedId);

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-3 h-[calc(100vh-3.5rem)]">
      <div className="space-y-3 overflow-auto">
        <div className="flex items-center gap-2 rounded border border-amber-glow/40 bg-amber-glow/5 px-3 py-2 font-mono text-[10px] text-amber-glow">
          <MapPinOff className="h-3.5 w-3.5" />
          Spatial map view unavailable — no camera position data exists on the backend (tracked in
          docs/FRONTEND_ARCHITECTURE.md §16). Showing real status grouped by location.
        </div>

        {camerasQuery.isLoading ? (
          <LoadingState label="Loading cameras…" />
        ) : camerasQuery.isError ? (
          <ErrorState label="Failed to load cameras." onRetry={() => void camerasQuery.refetch()} />
        ) : cameras.length === 0 ? (
          <EmptyState label="No cameras registered." />
        ) : (
          Array.from(groups.entries()).map(([location, group]) => (
            <Panel key={location} title={location}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {group.map((camera) => {
                  const threatCount = threatCountByCameraId.get(camera.id) ?? 0;
                  return (
                    <button
                      key={camera.id}
                      onClick={() => setSelectedId(camera.id)}
                      className={`text-left hud-panel rounded p-2 border transition ${
                        selectedId === camera.id
                          ? "border-primary/70 hud-panel-glow"
                          : "border-border hover:border-primary/40"
                      } ${threatCount > 0 ? "border-red-glow/60" : ""}`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 font-mono text-[11px]">
                          <CameraIcon className="h-3 w-3 text-muted-foreground" />
                          {camera.name}
                        </div>
                        <StatusDot status={camera.healthStatus()} />
                      </div>
                      {threatCount > 0 && (
                        <div className="mt-1 font-mono text-[9px] text-red-glow">
                          {threatCount} active threat{threatCount > 1 ? "s" : ""}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </Panel>
          ))
        )}
      </div>

      <Panel title={selected ? selected.name : "Select a camera"}>
        {!selected ? (
          <EmptyState label="Select a camera from the list." />
        ) : (
          <div className="space-y-3 font-mono text-[11px]">
            <div className="flex items-center gap-2">
              <StatusDot status={selected.healthStatus()} />
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {selected.healthStatus()}
              </span>
            </div>
            <DetailRow label="Location" value={selected.location ?? "Unassigned"} />
            <DetailRow label="FPS" value={String(fpsByCameraId.get(selected.id) ?? "—")} />
            <DetailRow label="Updated" value={selected.updatedAt.toLocaleString()} />

            <div className="hud-divider my-2" />
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Active Threats
            </div>
            {selectedThreats.length === 0 ? (
              <EmptyState label="None." />
            ) : (
              <div className="space-y-1">
                {selectedThreats.map((t) => (
                  <div key={t.trackId} className="flex items-center justify-between">
                    <span>
                      {t.weaponType} · {t.uniform}
                    </span>
                    <ThreatLevelBadge level={t.threatLevel} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}

function groupByLocation(cameras: Camera[]): Map<string, Camera[]> {
  const groups = new Map<string, Camera[]>();
  for (const camera of cameras) {
    const key = camera.location ?? "Unassigned";
    const list = groups.get(key) ?? [];
    list.push(camera);
    groups.set(key, list);
  }
  return groups;
}

function StatusDot({ status }: { status: "healthy" | "degraded" | "offline" }) {
  const color =
    status === "healthy"
      ? "var(--success)"
      : status === "degraded"
        ? "var(--amber-glow)"
        : "var(--red-glow)";
  return (
    <span
      className="h-2 w-2 rounded-full"
      style={{ background: color, boxShadow: `0 0 8px ${color}` }}
    />
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground uppercase tracking-widest text-[10px]">{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}
