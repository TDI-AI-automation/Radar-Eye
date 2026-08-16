import { Evidence } from "../models/Evidence";
import type { components } from "../../api/generated/schema";

type EvidenceItemDto = components["schemas"]["EvidenceItemSchema"];

export function toEvidenceDomain(dto: EvidenceItemDto): Evidence {
  return new Evidence(
    dto.evidence_id,
    dto.evidence_type,
    dto.incident_id,
    dto.camera_id,
    new Date(dto.captured_at),
    dto.download_url,
  );
}
