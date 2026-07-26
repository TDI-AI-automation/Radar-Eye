import { Incident } from "../models/Incident";
import { IncidentSummary } from "../models/IncidentSummary";
import type { components } from "../../api/generated/schema";

type IncidentDto = components["schemas"]["IncidentSchema"];
type IncidentSummaryDto = components["schemas"]["IncidentSummarySchema"];

export function toIncidentDomain(dto: IncidentDto): Incident {
  return new Incident(
    dto.incident_id,
    dto.camera_id,
    dto.track_id,
    dto.incident_type,
    dto.threat_level,
    dto.status,
    new Date(dto.created_at),
    new Date(dto.updated_at),
  );
}

export function toIncidentSummaryDomain(dto: IncidentSummaryDto): IncidentSummary {
  return new IncidentSummary(dto.incident_id, dto.camera_id, dto.threat_level, dto.status);
}
