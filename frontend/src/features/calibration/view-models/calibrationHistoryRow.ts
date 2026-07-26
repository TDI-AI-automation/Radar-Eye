import type { CameraCalibration } from "@/domain/models/CameraCalibration";

export interface CalibrationHistoryRowViewModel {
  id: string;
  cameraId: string;
  cameraName: string;
  pointCount: number | null;
  calibratedBy: string;
  createdAt: Date;
}

export function buildCalibrationHistoryRowViewModel(
  calibration: CameraCalibration,
  cameraName: string | undefined,
): CalibrationHistoryRowViewModel {
  return {
    id: calibration.id,
    cameraId: calibration.cameraId,
    cameraName: cameraName ?? calibration.cameraId,
    pointCount: calibration.referencePointCount(),
    calibratedBy: calibration.calibratedBy ?? "Unknown",
    createdAt: calibration.createdAt,
  };
}
