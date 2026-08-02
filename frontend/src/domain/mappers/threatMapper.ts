import { ThreatAssessment } from "../models/ThreatAssessment";
import type { components } from "../../api/generated/schema";

/** ActiveThreatSchema (GET /threats/active) "extends ThreatAssessmentSchema
 * with no additional fields for now" (shared/schemas/threat.py) -- field-
 * identical, reused for both the REST response and the /ws/threats
 * message body (ws/messages.ts::ThreatAssessmentMessage). */
type ActiveThreatDto = components["schemas"]["ActiveThreatSchema"];

export function toThreatAssessmentDomain(dto: ActiveThreatDto): ThreatAssessment {
  return new ThreatAssessment(
    dto.camera_id,
    dto.track_id,
    dto.weapon_type,
    dto.uniform,
    dto.zone,
    dto.threat_level,
  );
}
