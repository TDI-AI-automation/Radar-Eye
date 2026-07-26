import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/QueryState";
import { Search, Settings2, X } from "lucide-react";
import { useCameras, useCamerasHealth } from "@/queries/useCameras";
import { useUpdateCamera } from "@/features/cameras/hooks/useCameraMutations";
import {
  buildCameraRowViewModel,
  type CameraRowViewModel,
} from "@/features/cameras/view-models/cameraRow";
import { usePermission } from "@/auth/usePermission";
import type { CameraConnectionStatus } from "@/domain/models/Camera";

export const Route = createFileRoute("/cameras")({
  head: () => ({
    meta: [
      { title: "Camera Management — SENTINEL C2" },
      {
        name: "description",
        content: "Inventory, configuration, and health of all connected surveillance cameras.",
      },
      { property: "og:title", content: "Camera Management — SENTINEL C2" },
      {
        property: "og:description",
        content: "Inventory and configuration of all connected surveillance cameras.",
      },
    ],
  }),
  component: Cameras,
});

function Cameras() {
  const [q, setQ] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const canEdit = usePermission("admin");

  const camerasQuery = useCameras();
  const healthQuery = useCamerasHealth();

  const rows = useMemo<CameraRowViewModel[]>(() => {
    const cameras = camerasQuery.data ?? [];
    const healthById = new Map((healthQuery.data ?? []).map((h) => [h.camera_id, h]));
    return cameras
      .map((camera) => buildCameraRowViewModel(camera, healthById.get(camera.id)))
      .filter(
        (r) =>
          !q ||
          r.id.toLowerCase().includes(q.toLowerCase()) ||
          r.location.toLowerCase().includes(q.toLowerCase()),
      );
  }, [camerasQuery.data, healthQuery.data, q]);

  const editCamera = editId ? (camerasQuery.data ?? []).find((c) => c.id === editId) : undefined;

  return (
    <div className="p-3 space-y-3">
      <Panel
        title="Camera Inventory"
        actions={
          <div className="relative">
            <Search className="absolute left-2 top-1.5 h-3 w-3 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search ID or location"
              className="rounded border border-border bg-black/40 pl-6 pr-2 py-1 text-[11px] font-mono placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>
        }
      >
        {camerasQuery.isLoading ? (
          <LoadingState label="Loading cameras…" />
        ) : camerasQuery.isError ? (
          <ErrorState label="Failed to load cameras." onRetry={() => void camerasQuery.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState label={q ? "No cameras match your search." : "No cameras registered."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="text-[9px] uppercase tracking-widest text-muted-foreground text-left border-b border-border/60">
                  {["Camera", "Status", "FPS", "Last Frame", "Location", ""].map((h) => (
                    <th key={h} className="px-2 py-2 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-border/30 hover:bg-primary/5">
                    <td className="px-2 py-2 text-primary">{r.name}</td>
                    <td className="px-2 py-2">
                      <StatusPill status={r.status} label={r.statusLabel} />
                    </td>
                    <td className="px-2 py-2">{r.fps ?? "—"}</td>
                    <td className="px-2 py-2 text-muted-foreground">
                      {r.lastFrameAgeSeconds === null
                        ? "—"
                        : `${r.lastFrameAgeSeconds.toFixed(0)}s ago`}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">{r.location}</td>
                    <td className="px-2 py-2 text-right">
                      <button
                        onClick={() => setEditId(r.id)}
                        disabled={!canEdit}
                        title={canEdit ? "Edit camera" : "Administrator role required"}
                        className="text-primary hover:text-glow-cyan disabled:text-muted-foreground disabled:cursor-not-allowed"
                      >
                        <Settings2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {editCamera && (
        <EditCameraModal
          cameraId={editCamera.id}
          initialName={editCamera.name}
          initialLocation={editCamera.location ?? ""}
          initialStatus={editCamera.status}
          onClose={() => setEditId(null)}
        />
      )}
    </div>
  );
}

function EditCameraModal({
  cameraId,
  initialName,
  initialLocation,
  initialStatus,
  onClose,
}: {
  cameraId: string;
  initialName: string;
  initialLocation: string;
  initialStatus: CameraConnectionStatus;
  onClose: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [location, setLocation] = useState(initialLocation);
  const [status, setStatus] = useState<CameraConnectionStatus>(initialStatus);
  const updateCamera = useUpdateCamera();

  async function handleSave() {
    await updateCamera.mutateAsync({ cameraId, body: { name, location, status } });
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="hud-panel hud-corner rounded max-w-lg w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-primary">
            Configure {cameraId}
          </h3>
          <button onClick={onClose}>
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
        <div className="p-4 space-y-3 font-mono text-[11px]">
          {/* RM-12's CameraUpdateRequestSchema only supports name/location/status --
              no resolution/codec/confidence-threshold/detection-types/privacy-mask/
              firmware fields exist on the backend. Those prototype fields are not
              carried forward here rather than left as non-functional inputs. */}
          <Row label="Name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Row>
          <Row label="Location">
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Row>
          <Row label="Status">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as CameraConnectionStatus)}
              className="bg-black/40 border border-border rounded px-2 py-1"
            >
              <option value="CONNECTED">Connected</option>
              <option value="DISCONNECTED">Disconnected</option>
              <option value="RECONNECTING">Reconnecting</option>
            </select>
          </Row>

          {updateCamera.isError && (
            <p className="text-glow-red" role="alert">
              Failed to save changes.
            </p>
          )}

          <div className="flex gap-2 pt-2">
            <button
              onClick={() => void handleSave()}
              disabled={updateCamera.isPending}
              className="flex-1 rounded border border-primary/50 bg-primary/15 py-2 uppercase tracking-widest text-primary text-[10px] disabled:opacity-50"
            >
              {updateCamera.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function StatusPill({
  status,
  label,
}: {
  status: "healthy" | "degraded" | "offline";
  label: string;
}) {
  const map = {
    healthy: "text-success border-success/40 bg-success/10",
    offline: "text-red-glow border-red-glow/50 bg-red-glow/10",
    degraded: "text-amber-glow border-amber-glow/50 bg-amber-glow/10",
  };
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${map[status]}`}
    >
      {label}
    </span>
  );
}
