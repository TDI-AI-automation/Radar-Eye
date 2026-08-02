/**
 * Canonical ThreatLevel type + its label/color mapping. THREAT_ENGINE_SPEC.md's
 * six-value enum -- ThreatAssessment and Incident/IncidentSummary (distinct
 * backend entities that both carry a threat_level field) both import this
 * instead of each declaring their own copy of the union, and both
 * ThreatAssessment.severityLabel()/.displayColor() and ThreatLevelBadge
 * (src/components/shared/ThreatLevelBadge.tsx) delegate to the functions
 * below -- this is the one place the mapping is allowed to exist.
 */
export type ThreatLevel = "ALLY" | "OBSERVE" | "LOW" | "MEDIUM" | "HIGH" | "HUMAN_REVIEW";

export function threatLevelLabel(level: ThreatLevel): string {
  switch (level) {
    case "ALLY":
      return "Ally";
    case "OBSERVE":
      return "Observe";
    case "LOW":
      return "Low";
    case "MEDIUM":
      return "Medium";
    case "HIGH":
      return "High";
    case "HUMAN_REVIEW":
      return "Human Review";
  }
}

/** Returns a CSS custom-property reference (src/styles.css), not a
 * literal color -- stays theme-controlled. */
export function threatLevelColor(level: ThreatLevel): string {
  switch (level) {
    case "HIGH":
      return "var(--red-glow)";
    case "MEDIUM":
    case "HUMAN_REVIEW":
      return "var(--amber-glow)";
    case "LOW":
    case "OBSERVE":
      return "var(--primary)";
    case "ALLY":
      return "var(--success)";
  }
}
