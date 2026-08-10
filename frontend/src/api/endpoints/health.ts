import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type SystemHealthDto = components["schemas"]["SystemHealthSchema"];
type GPUHealthDto = components["schemas"]["GPUHealthSchema"];
type StorageHealthDto = components["schemas"]["StorageHealthSchema"];

export function getSystemHealth(): Promise<SystemHealthDto | null> {
  return apiClient.request<SystemHealthDto>("/health/system");
}

export function getGpuHealth(): Promise<GPUHealthDto | null> {
  return apiClient.request<GPUHealthDto>("/health/gpu");
}

export function getStorageHealth(): Promise<StorageHealthDto | null> {
  return apiClient.request<StorageHealthDto>("/health/storage");
}

/** Recording/evidence storage root -- a distinct filesystem path from
 * getStorageHealth()'s default target (apps/api/app/health/collector.py:
 * get_recording_health() calls get_storage_health(recording_storage_path)),
 * same StorageHealthSchema shape. */
export function getRecordingHealth(): Promise<StorageHealthDto | null> {
  return apiClient.request<StorageHealthDto>("/health/recording");
}
