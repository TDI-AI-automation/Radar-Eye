import type { Camera, CameraBrand } from "@/domain/models/Camera";
import type { CameraHealthDto } from "@/queries/useCameras";

export type CameraRowStatus = "healthy" | "degraded" | "offline";

export interface CameraRowViewModel {
  id: string;
  name: string;
  brand: CameraBrand | null;
  brandLabel: string;
  ipAddress: string | null;
  location: string;
  aiEnabled: boolean;
  recordingEnabled: boolean;
  connectionStatus: Camera["status"];
  connectionStatusLabel: string;
  /** FPS-derived health, distinct from connectionStatus (the raw Camera
   * Runtime-observed transport state) -- both surface on the row per the
   * Camera Management spec's "Connection Status" + "Health" columns. */
  health: CameraRowStatus;
  healthLabel: string;
  /** null when GET /health/cameras hasn't reported this camera yet, or the
   * backend's fps field is itself null -- rendered as "—", never 0. */
  fps: number | null;
  lastFrameAgeSeconds: number | null;
  lastSeenLabel: string;
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
  const lastFrameAgeSeconds = health?.last_frame_age_seconds ?? null;
  return {
    id: camera.id,
    name: camera.name,
    brand: camera.brand,
    brandLabel: brandLabel(camera.brand),
    ipAddress: camera.ipAddress,
    location: camera.location ?? "Unassigned",
    aiEnabled: camera.aiEnabled,
    recordingEnabled: camera.recordingEnabled,
    connectionStatus: camera.status,
    connectionStatusLabel: connectionStatusLabel(camera.status),
    health: camera.healthStatus(),
    healthLabel: healthLabel(camera.healthStatus()),
    fps: health?.fps ?? null,
    lastFrameAgeSeconds,
    lastSeenLabel: lastSeenLabel(lastFrameAgeSeconds),
  };
}

function connectionStatusLabel(status: Camera["status"]): string {
  switch (status) {
    case "CONNECTED":
      return "Connected";
    case "RECONNECTING":
      return "Reconnecting";
    case "DISCONNECTED":
      return "Disconnected";
  }
}

function healthLabel(status: CameraRowStatus): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "degraded":
      return "Degraded";
    case "offline":
      return "Offline";
  }
}

function lastSeenLabel(lastFrameAgeSeconds: number | null): string {
  return lastFrameAgeSeconds === null ? "—" : `${lastFrameAgeSeconds.toFixed(0)}s ago`;
}

const BRAND_LABELS: Record<CameraBrand, string> = {
  HIKVISION: "Hikvision",
  DAHUA: "Dahua",
  UNIVIEW: "Uniview",
  AXIS: "Axis",
  HANWHA: "Hanwha",
};

function brandLabel(brand: CameraBrand | null): string {
  return brand ? BRAND_LABELS[brand] : "—";
}
