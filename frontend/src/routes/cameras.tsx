import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/QueryState";
import { Search, Plus, Settings2, Trash2, X } from "lucide-react";
import { useCameras, useCamerasHealth } from "@/queries/useCameras";
import { useCameraBrands } from "@/features/cameras/hooks/useCameraBrands";
import {
  useCreateCamera,
  useUpdateCamera,
  useDeleteCamera,
} from "@/features/cameras/hooks/useCameraMutations";
import {
  buildCameraRowViewModel,
  type CameraRowViewModel,
} from "@/features/cameras/view-models/cameraRow";
import { usePermission } from "@/auth/usePermission";
import { AppError } from "@/api/AppError";
import type { Camera, CameraBrand } from "@/domain/models/Camera";

export const Route = createFileRoute("/cameras")({
  head: () => ({
    meta: [
      { title: "Camera Management — SENTINEL C2" },
      {
        name: "description",
        content: "Register, configure, and remove surveillance cameras.",
      },
      { property: "og:title", content: "Camera Management — SENTINEL C2" },
      {
        property: "og:description",
        content: "Register, configure, and remove surveillance cameras.",
      },
    ],
  }),
  component: Cameras,
});

function Cameras() {
  const [q, setQ] = useState("");
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);
  const [deletingCameraId, setDeletingCameraId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const canEdit = usePermission("admin");

  const camerasQuery = useCameras();
  const healthQuery = useCamerasHealth();
  const toggleAi = useUpdateCamera();
  const [togglingAiId, setTogglingAiId] = useState<string | null>(null);

  async function handleToggleAi(cameraId: string, currentlyEnabled: boolean) {
    setTogglingAiId(cameraId);
    try {
      await toggleAi.mutateAsync({ cameraId, body: { ai_enabled: !currentlyEnabled } });
    } catch {
      // Surfaced via toggleAi.isError below is per-mutation, not per-row --
      // a failed toggle just leaves the pill showing the last known state,
      // which is still correct (nothing changed server-side).
    } finally {
      setTogglingAiId(null);
    }
  }

  const rows = useMemo<CameraRowViewModel[]>(() => {
    const cameras = camerasQuery.data ?? [];
    const healthById = new Map((healthQuery.data ?? []).map((h) => [h.camera_id, h]));
    return cameras
      .map((camera) => buildCameraRowViewModel(camera, healthById.get(camera.id)))
      .filter(
        (r) =>
          !q ||
          r.name.toLowerCase().includes(q.toLowerCase()) ||
          r.location.toLowerCase().includes(q.toLowerCase()) ||
          (r.ipAddress ?? "").toLowerCase().includes(q.toLowerCase()),
      );
  }, [camerasQuery.data, healthQuery.data, q]);

  const editingCamera = editingCameraId
    ? (camerasQuery.data ?? []).find((c) => c.id === editingCameraId)
    : undefined;
  const deletingCamera = deletingCameraId
    ? (camerasQuery.data ?? []).find((c) => c.id === deletingCameraId)
    : undefined;

  return (
    <div className="p-3 space-y-3">
      <Panel
        title="Camera Management"
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1.5 h-3 w-3 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search name, IP, location"
                className="rounded border border-border bg-black/40 pl-6 pr-2 py-1 text-[11px] font-mono placeholder:text-muted-foreground focus:border-primary focus:outline-none"
              />
            </div>
            <button
              onClick={() => setAddOpen(true)}
              disabled={!canEdit}
              title={canEdit ? "Register a new camera" : "Administrator role required"}
              className="flex items-center gap-1 rounded border border-primary/50 bg-primary/15 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Camera
            </button>
          </div>
        }
      >
        {camerasQuery.isLoading ? (
          <LoadingState label="Loading cameras…" />
        ) : camerasQuery.isError ? (
          <ErrorState label="Failed to load cameras." onRetry={() => void camerasQuery.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            label={
              q
                ? "No cameras match your search."
                : "No cameras registered. Use Add Camera to register the first one."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="text-[9px] uppercase tracking-widest text-muted-foreground text-left border-b border-border/60">
                  {[
                    "Camera Name",
                    "Brand",
                    "IP Address",
                    "Location",
                    "AI Enabled",
                    "Recording Enabled",
                    "Connection Status",
                    "Health",
                    "Last Seen",
                    "Actions",
                  ].map((h) => (
                    <th key={h} className="px-2 py-2 font-normal whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-border/30 hover:bg-primary/5">
                    <td className="px-2 py-2 text-primary whitespace-nowrap">{r.name}</td>
                    <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
                      {r.brandLabel}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
                      {r.ipAddress ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
                      {r.location}
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <AiTogglePill
                        enabled={r.aiEnabled}
                        disabled={!canEdit || togglingAiId === r.id}
                        title={canEdit ? "Toggle AI" : "Administrator role required"}
                        onToggle={() => void handleToggleAi(r.id, r.aiEnabled)}
                      />
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <FlagPill enabled={r.recordingEnabled} />
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <StatusPill status={r.health} label={r.connectionStatusLabel} />
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <StatusPill status={r.health} label={r.healthLabel} />
                    </td>
                    <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
                      {r.lastSeenLabel}
                    </td>
                    <td className="px-2 py-2 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setEditingCameraId(r.id)}
                          disabled={!canEdit}
                          title={canEdit ? "Edit camera" : "Administrator role required"}
                          className="text-primary hover:text-glow-cyan disabled:text-muted-foreground disabled:cursor-not-allowed"
                        >
                          <Settings2 className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setDeletingCameraId(r.id)}
                          disabled={!canEdit}
                          title={canEdit ? "Delete camera" : "Administrator role required"}
                          className="text-red-glow hover:text-red-glow/70 disabled:text-muted-foreground disabled:cursor-not-allowed"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {addOpen && <CameraFormModal mode="add" onClose={() => setAddOpen(false)} />}

      {editingCamera && (
        <CameraFormModal
          mode="edit"
          camera={editingCamera}
          onClose={() => setEditingCameraId(null)}
        />
      )}

      {deletingCamera && (
        <DeleteCameraModal camera={deletingCamera} onClose={() => setDeletingCameraId(null)} />
      )}
    </div>
  );
}

const BRAND_VALUES = ["HIKVISION", "DAHUA", "UNIVIEW", "AXIS", "HANWHA"] as const;

const cameraFormSchema = z.object({
  name: z.string().min(1, "Camera name is required"),
  location: z.string(),
  brand: z.enum(BRAND_VALUES),
  model: z.string(),
  ipAddress: z
    .string()
    .min(1, "IP address is required")
    .regex(/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/, "Enter a valid IPv4 address"),
  port: z.string().refine((v) => !v || (/^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 65535), {
    message: "Port must be between 1 and 65535",
  }),
  username: z.string(),
  password: z.string(),
  transport: z.enum(["tcp", "udp"]),
  streamPath: z.string(),
  aiEnabled: z.boolean(),
  recordingEnabled: z.boolean(),
});

type CameraFormValues = z.infer<typeof cameraFormSchema>;

function toFormDefaults(camera: Camera | undefined): CameraFormValues {
  if (!camera) {
    return {
      name: "",
      location: "",
      brand: "HIKVISION",
      model: "",
      ipAddress: "",
      port: "",
      username: "",
      password: "",
      transport: "tcp",
      streamPath: "",
      aiEnabled: false,
      recordingEnabled: false,
    };
  }
  return {
    name: camera.name,
    location: camera.location ?? "",
    brand: camera.brand ?? "HIKVISION",
    model: camera.model ?? "",
    ipAddress: camera.ipAddress ?? "",
    port: camera.port ? String(camera.port) : "",
    username: camera.username ?? "",
    password: "",
    transport: camera.transport === "udp" ? "udp" : "tcp",
    streamPath: camera.streamPath ?? "",
    aiEnabled: camera.aiEnabled,
    recordingEnabled: camera.recordingEnabled,
  };
}

function CameraFormModal({
  mode,
  camera,
  onClose,
}: {
  mode: "add" | "edit";
  camera?: Camera;
  onClose: () => void;
}) {
  const brandsQuery = useCameraBrands();
  const createCamera = useCreateCamera();
  const updateCamera = useUpdateCamera();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<CameraFormValues>({
    resolver: zodResolver(cameraFormSchema),
    defaultValues: toFormDefaults(camera),
  });

  const selectedBrand = watch("brand");
  const selectedBrandInfo = brandsQuery.data?.find((b) => b.brand === selectedBrand);

  async function onSubmit(values: CameraFormValues) {
    setSubmitError(null);
    try {
      if (mode === "add") {
        await createCamera.mutateAsync({
          name: values.name,
          location: values.location || null,
          brand: values.brand,
          model: values.model || null,
          ip_address: values.ipAddress,
          port: values.port ? Number(values.port) : null,
          stream_path: values.streamPath || null,
          username: values.username || null,
          password: values.password || null,
          transport: values.transport,
          ai_enabled: values.aiEnabled,
          recording_enabled: values.recordingEnabled,
        });
      } else if (camera) {
        const body: Parameters<typeof updateCamera.mutateAsync>[0]["body"] = {
          name: values.name,
          location: values.location || null,
          brand: values.brand,
          model: values.model || null,
          ip_address: values.ipAddress,
          port: values.port ? Number(values.port) : null,
          stream_path: values.streamPath || null,
          username: values.username || null,
          transport: values.transport,
          ai_enabled: values.aiEnabled,
          recording_enabled: values.recordingEnabled,
        };
        // password is write-only -- omit entirely when left blank so the
        // backend keeps the existing one, rather than sending "" and
        // clearing it.
        if (values.password) {
          body.password = values.password;
        }
        await updateCamera.mutateAsync({ cameraId: camera.id, body });
      }
      onClose();
    } catch (err) {
      setSubmitError(err instanceof AppError ? err.message : "Failed to save camera.");
    }
  }

  const isPending = createCamera.isPending || updateCamera.isPending || isSubmitting;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="hud-panel hud-corner rounded max-w-2xl w-full my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-primary">
            {mode === "add" ? "Add Camera" : `Configure ${camera?.name}`}
          </h3>
          <button onClick={onClose}>
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        <form
          onSubmit={(e) => void handleSubmit(onSubmit)(e)}
          className="p-4 space-y-3 font-mono text-[11px]"
        >
          <Field label="Camera Name" error={errors.name?.message}>
            <input
              {...register("name")}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Location">
            <input
              {...register("location")}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Brand" error={errors.brand?.message}>
            <select
              {...register("brand")}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            >
              {BRAND_VALUES.map((b) => (
                <option key={b} value={b}>
                  {brandsQuery.data?.find((info) => info.brand === b)?.label ?? b}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Model (optional)">
            <input
              {...register("model")}
              placeholder="e.g. DS-2CD2143G0-I"
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="IP Address" error={errors.ipAddress?.message}>
            <input
              {...register("ipAddress")}
              placeholder="192.168.1.10"
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Port" error={errors.port?.message}>
            <input
              {...register("port")}
              placeholder={selectedBrandInfo ? `Default: ${selectedBrandInfo.default_port}` : "554"}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Username">
            <input
              {...register("username")}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Password">
            <input
              type="password"
              {...register("password")}
              placeholder={mode === "edit" ? "Leave blank to keep current password" : ""}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Transport">
            <select
              {...register("transport")}
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            >
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
            </select>
          </Field>
          <Field label="Stream" error={errors.streamPath?.message}>
            <input
              {...register("streamPath")}
              placeholder={
                selectedBrandInfo ? `Default: ${selectedBrandInfo.default_stream_path}` : ""
              }
              className="bg-black/40 border border-border rounded px-2 py-1 flex-1 ml-3"
            />
          </Field>
          <Field label="Recording Enabled">
            <input type="checkbox" {...register("recordingEnabled")} className="h-4 w-4" />
          </Field>
          <Field label="AI Enabled">
            <input type="checkbox" {...register("aiEnabled")} className="h-4 w-4" />
          </Field>
          <p className="text-muted-foreground text-[10px]">
            The RTSP URL is generated automatically from Brand + IP + Port + Stream + credentials.
            It is never entered manually and never displayed.
          </p>

          {submitError && (
            <p className="text-glow-red" role="alert">
              {submitError}
            </p>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={isPending}
              className="flex-1 rounded border border-primary/50 bg-primary/15 py-2 uppercase tracking-widest text-primary text-[10px] disabled:opacity-50"
            >
              {isPending ? "Saving…" : mode === "add" ? "Register Camera" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</span>
        {children}
      </div>
      {error && (
        <p className="text-glow-red text-right text-[10px] mt-0.5" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function DeleteCameraModal({ camera, onClose }: { camera: Camera; onClose: () => void }) {
  const deleteCamera = useDeleteCamera();
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setError(null);
    try {
      await deleteCamera.mutateAsync(camera.id);
      onClose();
    } catch (err) {
      setError(err instanceof AppError ? err.message : "Failed to delete camera.");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="hud-panel hud-corner rounded max-w-md w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-red-glow">
            Delete Camera
          </h3>
          <button onClick={onClose}>
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
        <div className="p-4 space-y-3 font-mono text-[11px]">
          <p>
            Delete <span className="text-primary">{camera.name}</span>? This removes it from Camera
            Runtime and cannot be undone.
          </p>
          {error && (
            <p className="text-glow-red" role="alert">
              {error}
            </p>
          )}
          <div className="flex gap-2 pt-2">
            <button
              onClick={onClose}
              className="flex-1 rounded border border-border py-2 uppercase tracking-widest text-muted-foreground text-[10px]"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleDelete()}
              disabled={deleteCamera.isPending}
              className="flex-1 rounded border border-red-glow/50 bg-red-glow/15 py-2 uppercase tracking-widest text-red-glow text-[10px] disabled:opacity-50"
            >
              {deleteCamera.isPending ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FlagPill({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${
        enabled
          ? "text-success border-success/40 bg-success/10"
          : "text-muted-foreground border-border bg-black/20"
      }`}
    >
      {enabled ? "On" : "Off"}
    </span>
  );
}

/** Same visual language as FlagPill, but clickable -- AI is the one flag
 * operators need to flip from the list itself (RM-12 Design Principle 3:
 * AI never auto-starts, so this is the day-to-day on/off control, not
 * buried in the Edit modal). Video visibility is unaffected either way --
 * Live Monitoring's WebRTC stream keeps flowing regardless of this
 * setting, only the overlays it carries change. */
function AiTogglePill({
  enabled,
  disabled,
  title,
  onToggle,
}: {
  enabled: boolean;
  disabled: boolean;
  title: string;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest disabled:cursor-not-allowed disabled:opacity-50 ${
        enabled
          ? "text-success border-success/40 bg-success/10 hover:bg-success/20"
          : "text-muted-foreground border-border bg-black/20 hover:bg-black/30"
      }`}
    >
      {enabled ? "On" : "Off"}
    </button>
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
