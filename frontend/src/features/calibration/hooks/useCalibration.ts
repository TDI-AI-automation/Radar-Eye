import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listCalibrationCameras,
  listCalibrationResults,
  getCameraCalibration,
  startCalibration,
  validateCalibration,
} from "@/api/endpoints/calibration";
import { toCameraDomain } from "@/domain/mappers/cameraMapper";
import { toCameraCalibrationDomain } from "@/domain/mappers/calibrationMapper";
import { AppError } from "@/api/AppError";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";
import type { components } from "@/api/generated/schema";

export function useCalibrationCameras() {
  return useQuery({
    queryKey: queryKeys.calibration.cameras(),
    queryFn: async () => {
      const dtos = (await listCalibrationCameras()) ?? [];
      return dtos.map(toCameraDomain);
    },
    staleTime: STALE_TIME.reference,
  });
}

export function useCalibrationResults() {
  return useQuery({
    queryKey: queryKeys.calibration.results(),
    queryFn: async () => {
      const dtos = (await listCalibrationResults()) ?? [];
      return dtos.map(toCameraCalibrationDomain);
    },
    staleTime: STALE_TIME.reference,
  });
}

/** Returns null (not an error) when the camera has never been calibrated
 * -- GET /calibration/{id} 404s in that case, which is an expected,
 * displayable "not yet calibrated" state, not a failure. */
export function useCameraCalibration(cameraId: string | null) {
  return useQuery({
    queryKey: queryKeys.calibration.forCamera(cameraId ?? ""),
    queryFn: async () => {
      if (!cameraId) return null;
      try {
        const dto = await getCameraCalibration(cameraId);
        return dto ? toCameraCalibrationDomain(dto) : null;
      } catch (err) {
        if (err instanceof AppError && err.isNotFound) return null;
        throw err;
      }
    },
    enabled: cameraId !== null,
    staleTime: STALE_TIME.reference,
  });
}

/** Operator-gated on the backend; callers must also gate the UI
 * affordance with usePermission("operator") per §12. */
export function useStartCalibration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Parameters<typeof startCalibration>[0]) => {
      const dto = await startCalibration(body);
      return dto ? toCameraCalibrationDomain(dto) : null;
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.calibration.results() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.calibration.forCamera(variables.camera_id),
      });
    },
  });
}

export function useValidateCalibration() {
  return useMutation({
    mutationFn: (body: components["schemas"]["CalibrationValidateRequestSchema"]) =>
      validateCalibration(body),
  });
}
