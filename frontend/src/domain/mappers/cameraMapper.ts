import { Camera } from "../models/Camera";
import type { components } from "../../api/generated/schema";

type CameraDto = components["schemas"]["CameraSchema"];

export function toCameraDomain(dto: CameraDto): Camera {
  return new Camera(
    dto.camera_id,
    dto.name,
    dto.location ?? null,
    dto.status,
    new Date(dto.created_at),
    new Date(dto.updated_at),
  );
}
