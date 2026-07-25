/**
 * Transport-level types matching Radar-Eye backend's
 * shared/schemas/api.py::ApiResponse[T]/ApiError exactly. This is the ONE
 * place that shape is declared by hand -- everything else in src/api/
 * generated/ (Phase 1) is produced from the backend's OpenAPI schema.
 */

export interface ApiError {
  code: string;
  message: string;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiError | null;
}
