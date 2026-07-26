import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { Panel, Bar } from "@/components/hud/Panel";
import { LoadingState, ErrorState } from "@/components/shared/QueryState";
import { DisabledFeaturePanel } from "@/components/shared/DisabledFeaturePanel";
import { Cpu, HardDrive, Database, Camera as CameraIcon } from "lucide-react";
import {
  useSystemHealth,
  useGpuHealth,
  useStorageHealth,
  useRecordingHealth,
} from "@/features/health/hooks/useHealth";
import { useCameras, useCamerasHealth } from "@/queries/useCameras";
import {
  buildComponentRows,
  formatBytes,
  statusTone,
} from "@/features/health/view-models/healthViewModels";

export const Route = createFileRoute("/health")({
  head: () => ({
    meta: [
      { title: "System Health — SENTINEL C2" },
      {
        name: "description",
        content: "Real-time health of GPU, storage, cameras, and core subsystems.",
      },
      { property: "og:title", content: "System Health — SENTINEL C2" },
      {
        property: "og:description",
        content: "Real-time health of GPU, storage, cameras, and core subsystems.",
      },
    ],
  }),
  component: Health,
});

const TONE_CLASS: Record<string, string> = {
  success: "text-success border-success/40 bg-success/10",
  amber: "text-amber-glow border-amber-glow/40 bg-amber-glow/10",
  red: "text-red-glow border-red-glow/40 bg-red-glow/10",
  muted: "text-muted-foreground border-border bg-black/20",
};

/**
 * CLAUDE.md's primary deployment target is a single Jetson AGX Orin --
 * the prototype's CPU/Memory/Ambient/Network-Uplink/MQTT/Notification-Bus
 * panels have no backing endpoint anywhere in RM-12 and are not carried
 * forward (docs/FRONTEND_ARCHITECTURE.md's Phase 2 checkpoint has the
 * full list of what was dropped and why). GPU/Storage/Recording/Cameras/
 * component-status are all real (apps/api/app/health/collector.py).
 * Event Log Stream has no backing endpoint either (no GET /audit-log
 * exists yet, docs/FRONTEND_ARCHITECTURE.md §10) -- shown as an explicit
 * disabled panel, matching Settings' existing precedent for deferred
 * tabs, rather than removed or filled with fabricated entries.
 */
function Health() {
  const systemQuery = useSystemHealth();
  const gpuQuery = useGpuHealth();
  const storageQuery = useStorageHealth();
  const recordingQuery = useRecordingHealth();
  const camerasQuery = useCameras();
  const cameraHealthQuery = useCamerasHealth();

  const componentRows = useMemo(
    () => buildComponentRows(systemQuery.data?.components),
    [systemQuery.data],
  );

  const cameraHealthById = useMemo(
    () => new Map((cameraHealthQuery.data ?? []).map((h) => [h.camera_id, h])),
    [cameraHealthQuery.data],
  );

  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <Panel title="Overall Status">
          {systemQuery.isLoading ? (
            <LoadingState />
          ) : systemQuery.isError ? (
            <ErrorState onRetry={() => void systemQuery.refetch()} />
          ) : (
            <span
              className={`inline-flex items-center rounded border px-3 py-1.5 font-mono text-sm uppercase tracking-widest ${TONE_CLASS[statusTone(systemQuery.data?.status)]}`}
            >
              {systemQuery.data?.status ?? "Unknown"}
            </span>
          )}
        </Panel>

        <Panel title="GPU">
          {gpuQuery.isLoading ? (
            <LoadingState />
          ) : gpuQuery.isError ? (
            <ErrorState onRetry={() => void gpuQuery.refetch()} />
          ) : gpuQuery.data?.utilization_percent == null ? (
            <div className="flex items-center gap-3">
              <Cpu className="h-5 w-5 text-muted-foreground" />
              <span className="text-[11px] font-mono text-muted-foreground">
                GPU metrics unavailable in this environment
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="hud-panel rounded p-2 border-primary/30">
                <Cpu className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1">
                <div className="font-mono text-2xl font-bold text-glow-cyan">
                  {gpuQuery.data.utilization_percent.toFixed(0)}%
                </div>
                <div className="text-[10px] font-mono text-muted-foreground">
                  {gpuQuery.data.temperature_celsius != null
                    ? `${gpuQuery.data.temperature_celsius.toFixed(0)}°C · `
                    : ""}
                  {gpuQuery.data.memory_used_mb != null && gpuQuery.data.memory_total_mb != null
                    ? `${(gpuQuery.data.memory_used_mb / 1024).toFixed(1)} / ${(gpuQuery.data.memory_total_mb / 1024).toFixed(1)} GB`
                    : ""}
                </div>
              </div>
            </div>
          )}
        </Panel>

        <StoragePanel title="Storage · Evidence" icon={HardDrive} query={storageQuery} />
        <StoragePanel title="Storage · Recording" icon={HardDrive} query={recordingQuery} />

        <Panel title="Cameras">
          {systemQuery.isLoading ? (
            <LoadingState />
          ) : systemQuery.isError ? (
            <ErrorState onRetry={() => void systemQuery.refetch()} />
          ) : (
            <div className="flex items-center gap-3">
              <div className="hud-panel rounded p-2 border-primary/30">
                <CameraIcon className="h-5 w-5 text-primary" />
              </div>
              <div className="font-mono text-[11px] space-y-0.5">
                <div className="text-success">
                  {systemQuery.data?.cameras.connected_count ?? 0} Connected
                </div>
                <div className="text-amber-glow">
                  {systemQuery.data?.cameras.reconnecting_count ?? 0} Reconnecting
                </div>
                <div className="text-red-glow">
                  {systemQuery.data?.cameras.disconnected_count ?? 0} Disconnected
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Components">
          {systemQuery.isLoading ? (
            <LoadingState />
          ) : systemQuery.isError ? (
            <ErrorState onRetry={() => void systemQuery.refetch()} />
          ) : (
            <div className="flex items-center gap-3">
              <div className="hud-panel rounded p-2 border-primary/30">
                <Database className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 flex flex-wrap gap-1.5">
                {componentRows.map((c) => (
                  <span
                    key={c.name}
                    className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest ${TONE_CLASS[c.tone]}`}
                  >
                    {c.name}: {c.state}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Camera Health Distribution">
          {camerasQuery.isLoading ? (
            <LoadingState />
          ) : camerasQuery.isError ? (
            <ErrorState onRetry={() => void camerasQuery.refetch()} />
          ) : (camerasQuery.data ?? []).length === 0 ? (
            <span className="font-mono text-[11px] text-muted-foreground">
              No cameras registered.
            </span>
          ) : (
            <div className="grid grid-cols-12 gap-1">
              {(camerasQuery.data ?? []).map((camera) => {
                const health = cameraHealthById.get(camera.id);
                const tone =
                  health?.status === "CONNECTED"
                    ? "var(--success)"
                    : health?.status === "RECONNECTING"
                      ? "var(--amber-glow)"
                      : "var(--red-glow)";
                return (
                  <div
                    key={camera.id}
                    title={`${camera.name} · ${health?.status ?? camera.status}`}
                    className="aspect-square rounded"
                    style={{ background: tone, opacity: 0.85, boxShadow: `0 0 8px ${tone}` }}
                  />
                );
              })}
            </div>
          )}
        </Panel>

        <Panel title="Event Log Stream">
          <DisabledFeaturePanel reason="Not yet available — awaiting a GET /audit-log endpoint (docs/FRONTEND_ARCHITECTURE.md §10)." />
        </Panel>
      </div>
    </div>
  );
}

function StoragePanel({
  title,
  icon: Icon,
  query,
}: {
  title: string;
  icon: typeof HardDrive;
  query: ReturnType<typeof useStorageHealth>;
}) {
  return (
    <Panel title={title}>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : (
        <>
          <div className="flex items-center gap-3">
            <div className="hud-panel rounded p-2 border-primary/30">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <div className="font-mono text-2xl font-bold text-glow-cyan">
                {query.data?.usage_percent.toFixed(0) ?? 0}%
              </div>
              <div className="text-[10px] font-mono text-muted-foreground">
                {query.data
                  ? `${formatBytes(query.data.used_bytes)} / ${formatBytes(query.data.total_bytes)}`
                  : ""}
              </div>
            </div>
          </div>
          <div className="mt-3">
            <Bar
              value={query.data?.usage_percent ?? 0}
              tone={
                (query.data?.usage_percent ?? 0) > 95
                  ? "red"
                  : (query.data?.usage_percent ?? 0) > 85
                    ? "amber"
                    : "success"
              }
            />
          </div>
        </>
      )}
    </Panel>
  );
}
