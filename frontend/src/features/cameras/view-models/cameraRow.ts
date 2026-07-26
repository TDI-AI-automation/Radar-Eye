import type { Camera } from "@/domain/models/Camera";
import type { CameraHealthDto } from "@/queries/useCameras";

export type CameraRowStatus = "healthy" | "degraded" | "offline";

export interface CameraRowViewModel {
  id: string;
  name: string;
  location: string;
  status: CameraRowStatus;
  statusLabel: string;
  /** null when GET /health/cameras hasn't reported this camera yet, or the
   * backend's fps field is itself null -- rendered as "—", never 0. */
  fps: number | null;
  lastFrameAgeSeconds: number | null;
}

/**
 * Joins Camera (GET /cameras) with its CameraHealthSchema entry
 * (GET /health/cameras, matched by camera_id) into one display-ready row.
 * This join -- not a mapper's job (two different DTOs) and not a domain
 * model's job (Camera mirrors CameraSchema only, per its own docstring) --
 * lives here, at the view-model layer, matching the "pure functions,
 * plain inputs/outputs" convention already used elsewhere (domain/
 * threatLevel.ts, domain/incidentStatus.ts).
 */
export function buildCameraRowViewModel(
  camera: Camera,
  health: CameraHealthDto | undefined,
): CameraRowViewModel {
  return {
    id: camera.id,
    name: camera.name,
    location: camera.location ?? "Unassigned",
    status: camera.healthStatus(),
    statusLabel: statusLabel(camera.healthStatus()),
    fps: health?.fps ?? null,
    lastFrameAgeSeconds: health?.last_frame_age_seconds ?? null,
  };
}

function statusLabel(status: CameraRowStatus): string {
  switch (status) {
    case "healthy":
      return "Online";
    case "degraded":
      return "Reconnecting";
    case "offline":
      return "Offline";
  }
}
