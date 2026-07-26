import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type CameraDto = components["schemas"]["CameraSchema"];
type CameraHealthDto = components["schemas"]["CameraHealthSchema"];
type CameraUpdateRequest = components["schemas"]["CameraUpdateRequestSchema"];

export function listCameras(): Promise<CameraDto[] | null> {
  return apiClient.request<CameraDto[]>("/cameras");
}

/** GET /health/cameras -- health for every registered camera in one call
 * (fps, last_frame_age_seconds), joined client-side with listCameras() by
 * camera_id rather than N per-camera requests. */
export function listCamerasHealth(): Promise<CameraHealthDto[] | null> {
  return apiClient.request<CameraHealthDto[]>("/health/cameras");
}

/** PATCH /cameras/{id} -- admin-only on the backend (require_role(ROLE_ADMIN)).
 * Only name/location/status are updatable; RTSP/stream config is out of
 * scope for this route (apps/api/app/routers/cameras.py). */
export function updateCamera(
  cameraId: string,
  body: CameraUpdateRequest,
): Promise<CameraDto | null> {
  return apiClient.request<CameraDto>(`/cameras/${cameraId}`, {
    method: "PATCH",
    body,
  });
}
