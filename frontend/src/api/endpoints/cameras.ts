import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type CameraDto = components["schemas"]["CameraSchema"];
type CameraHealthDto = components["schemas"]["CameraHealthSchema"];
type CameraUpdateRequest = components["schemas"]["CameraUpdateRequestSchema"];
type CameraCreateRequest = components["schemas"]["CameraCreateRequestSchema"];
export type CameraBrandInfoDto = components["schemas"]["CameraBrandInfoSchema"];

export function listCameras(): Promise<CameraDto[] | null> {
  return apiClient.request<CameraDto[]>("/cameras");
}

/** GET /health/cameras -- health for every registered camera in one call
 * (fps, last_frame_age_seconds), joined client-side with listCameras() by
 * camera_id rather than N per-camera requests. */
export function listCamerasHealth(): Promise<CameraHealthDto[] | null> {
  return apiClient.request<CameraHealthDto[]>("/health/cameras");
}

/** GET /cameras/brands -- the Add/Edit Camera form's only source of brand
 * choices and their default port/stream path (apps.api.app.services.
 * rtsp_url_generator is the single source of truth; this call is how the
 * frontend avoids hardcoding a second copy of it). */
export function listCameraBrands(): Promise<CameraBrandInfoDto[] | null> {
  return apiClient.request<CameraBrandInfoDto[]>("/cameras/brands");
}

/** POST /cameras -- admin-only. The operator supplies brand + IP +
 * credentials, never a raw RTSP URL; the backend generates and stores it. */
export function createCamera(body: CameraCreateRequest): Promise<CameraDto | null> {
  return apiClient.request<CameraDto>("/cameras", {
    method: "POST",
    body,
  });
}

/** PATCH /cameras/{id} -- admin-only on the backend (require_role(ROLE_ADMIN)).
 * Accepts name/location/ai_enabled/recording_enabled plus connection fields
 * (brand/ip_address/port/username/password/transport/stream_path) -- any
 * connection field present regenerates the stored RTSP URL server-side. */
export function updateCamera(
  cameraId: string,
  body: CameraUpdateRequest,
): Promise<CameraDto | null> {
  return apiClient.request<CameraDto>(`/cameras/${cameraId}`, {
    method: "PATCH",
    body,
  });
}

/** DELETE /cameras/{id} -- admin-only. 409s (AppError) if the camera has
 * existing incidents/review items/recordings -- that history is never
 * cascade-deleted; the caller should surface that as "resolve or export
 * that history first" rather than retrying. */
export function deleteCamera(cameraId: string): Promise<null> {
  return apiClient.request<null>(`/cameras/${cameraId}`, {
    method: "DELETE",
  });
}
