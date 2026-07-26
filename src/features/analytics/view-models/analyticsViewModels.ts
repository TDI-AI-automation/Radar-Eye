import { threatLevelLabel, threatLevelColor, type ThreatLevel } from "@/domain/threatLevel";
import type { components } from "@/api/generated/schema";

/**
 * Pass-through view-model layer for Analytics -- per docs/
 * FRONTEND_ARCHITECTURE.md §11 Finding 3, aggregate/reporting data has no
 * business behavior to model, so there is no domain class here; these
 * functions turn the raw sparse count dicts directly into display-ready
 * arrays (every known enum value present, missing counts defaulted to 0,
 * consistent ordering), which is as far as this data needs to go.
 */

const THREAT_LEVELS: ThreatLevel[] = ["HIGH", "MEDIUM", "HUMAN_REVIEW", "LOW", "OBSERVE", "ALLY"];

export interface ThreatLevelCountRow {
  level: ThreatLevel;
  label: string;
  color: string;
  count: number;
}

export function buildThreatLevelCounts(
  dto: components["schemas"]["ThreatAnalyticsSchema"] | null | undefined,
): ThreatLevelCountRow[] {
  const counts = dto?.counts_by_threat_level ?? {};
  return THREAT_LEVELS.map((level) => ({
    level,
    label: threatLevelLabel(level),
    color: threatLevelColor(level),
    count: counts[level] ?? 0,
  }));
}

type IncidentStatus = components["schemas"]["IncidentStatus"];
const INCIDENT_STATUSES: IncidentStatus[] = [
  "NEW",
  "ACTIVE",
  "ACKNOWLEDGED",
  "RESOLVED",
  "ARCHIVED",
];

export interface IncidentStatusCountRow {
  status: IncidentStatus;
  count: number;
}

export function buildIncidentStatusCounts(
  dto: components["schemas"]["IncidentAnalyticsSchema"] | null | undefined,
): IncidentStatusCountRow[] {
  const counts = dto?.counts_by_status ?? {};
  return INCIDENT_STATUSES.map((status) => ({ status, count: counts[status] ?? 0 }));
}

export interface TopCameraRow {
  cameraId: string;
  incidentCount: number;
}

/** Sorted descending, top N by incident count. Camera *names* require
 * joining against GET /cameras (queries/useCameras.ts) -- done at the
 * screen level, not here, since this function only has the analytics DTO
 * to work with. */
export function buildTopCamerasByIncidents(
  dto: components["schemas"]["CameraAnalyticsSchema"] | null | undefined,
  limit = 5,
): TopCameraRow[] {
  const counts = dto?.incident_counts_by_camera ?? {};
  return Object.entries(counts)
    .map(([cameraId, incidentCount]) => ({ cameraId, incidentCount }))
    .sort((a, b) => b.incidentCount - a.incidentCount)
    .slice(0, limit);
}
