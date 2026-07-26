/** Pass-through view-model layer for Health -- same exception as Analytics
 * (docs/FRONTEND_ARCHITECTURE.md §11 Finding 3): these are facts about
 * hardware/storage, not business entities with behavior. */

/** shared/schemas/health.py::HealthStatus -- a plain Literal, not a
 * Pydantic model, so it has no standalone entry in the generated schema
 * (it's inlined wherever SystemHealthSchema.status is typed). Declared by
 * hand here for that reason, same category as ws/messages.ts's gap. */
export type SystemHealthStatus = "healthy" | "degraded" | "unhealthy";

export type HealthTone = "success" | "amber" | "red" | "muted";

export function statusTone(status: SystemHealthStatus | undefined): HealthTone {
  switch (status) {
    case "healthy":
      return "success";
    case "degraded":
      return "amber";
    case "unhealthy":
      return "red";
    default:
      return "muted";
  }
}

export interface ComponentRow {
  name: string;
  state: string;
  tone: HealthTone;
}

/** apps/api/app/health/collector.py::get_system_health() always populates
 * exactly these 5 keys (database/event_bus/gpu/storage/cameras) with one
 * of "healthy"/"degraded"/"unhealthy"/"unavailable" -- the schema types
 * the dict as free-text, so unrecognized values fall back to a neutral
 * tone rather than assuming the fixed set holds forever. */
function componentStateTone(state: string): HealthTone {
  switch (state) {
    case "healthy":
      return "success";
    case "degraded":
      return "amber";
    case "unhealthy":
      return "red";
    default:
      return "muted";
  }
}

export function buildComponentRows(dict: Record<string, string> | undefined): ComponentRow[] {
  return Object.entries(dict ?? {}).map(([name, state]) => ({
    name,
    state,
    tone: componentStateTone(state),
  }));
}

export function bytesToGiB(bytes: number): number {
  return bytes / 1024 ** 3;
}

export function formatBytes(bytes: number): string {
  return `${bytesToGiB(bytes).toFixed(1)} GB`;
}
