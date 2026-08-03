import { Camera } from "../models/Camera";
import type { components } from "../../api/generated/schema";

type CameraDto = components["schemas"]["CameraSchema"];

export function toCameraDomain(dto: CameraDto): Camera {
  return new Camera(
    dto.camera_id,
    dto.name,
    dto.location ?? null,
    dto.status,
    dto.ai_enabled,
    dto.recording_enabled,
    dto.brand ?? null,
    dto.model ?? null,
    dto.ip_address ?? null,
    dto.port ?? null,
    dto.stream_path ?? null,
    dto.username ?? null,
    dto.transport ?? null,
    new Date(dto.created_at),
    new Date(dto.updated_at),
  );
}
