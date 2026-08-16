import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type CameraDto = components["schemas"]["CameraSchema"];
type CameraCalibrationDto = components["schemas"]["CameraCalibrationSchema"];
type CalibrationStartRequest = components["schemas"]["CalibrationStartRequestSchema"];
type CalibrationValidateRequest = components["schemas"]["CalibrationValidateRequestSchema"];
type CalibrationValidationResultDto = components["schemas"]["CalibrationValidationResultSchema"];

export function listCalibrationCameras(): Promise<CameraDto[] | null> {
  return apiClient.request<CameraDto[]>("/calibration/cameras");
}

/** Full historical log across every camera (append-only, never mutated --
 * apps/api/app/repositories/camera.py::CameraCalibrationRepository's own
 * docstring), sorted newest-first by the backend. */
export function listCalibrationResults(): Promise<CameraCalibrationDto[] | null> {
  return apiClient.request<CameraCalibrationDto[]>("/calibration/results");
}

/** 404s if the camera has never been calibrated -- caller must handle
 * that as an empty state, not an error. */
export function getCameraCalibration(cameraId: string): Promise<CameraCalibrationDto | null> {
  return apiClient.request<CameraCalibrationDto>(`/calibration/${cameraId}`);
}

/** Operator-gated. Requires >= MIN_REFERENCE_POINTS (4,
 * services/calibration/types.py) or the backend 422s. */
export function startCalibration(
  body: CalibrationStartRequest,
): Promise<CameraCalibrationDto | null> {
  return apiClient.request<CameraCalibrationDto>("/calibration/start", {
    method: "POST",
    body,
  });
}

/** Operator-gated. Projects one image point through the camera's current
 * calibration -- for the operator to visually confirm against a known
 * real-world point (services/calibration/service.py::estimate()). */
export function validateCalibration(
  body: CalibrationValidateRequest,
): Promise<CalibrationValidationResultDto | null> {
  return apiClient.request<CalibrationValidationResultDto>("/calibration/validate", {
    method: "POST",
    body,
  });
}
