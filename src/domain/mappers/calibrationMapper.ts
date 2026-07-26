import { CameraCalibration } from "../models/CameraCalibration";
import type { components } from "../../api/generated/schema";

type CameraCalibrationDto = components["schemas"]["CameraCalibrationSchema"];

export function toCameraCalibrationDomain(dto: CameraCalibrationDto): CameraCalibration {
  return new CameraCalibration(
    dto.calibration_id,
    dto.camera_id,
    dto.reference_points,
    dto.calibrated_by ?? null,
    new Date(dto.created_at),
  );
}
