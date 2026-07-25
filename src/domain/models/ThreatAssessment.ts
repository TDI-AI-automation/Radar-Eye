/**
 * ThreatAssessment domain model.
 *
 * Mirrors Radar-Eye backend's ThreatAssessmentEvent /
 * shared/schemas/threat.py::ThreatAssessmentSchema. The five field values
 * below (weaponType, uniform, zone, threatLevel value sets) are the exact
 * enums THREAT_ENGINE_SPEC.md and shared/constants/*.py define -- do not
 * invent new labels or values here; if the backend's set changes, this file
 * changes to match it, never the other way around (per the "backend must
 * not adapt to prototype assumptions" direction).
 */

export type WeaponType = "none" | "non_lethal" | "melee_lethal" | "ranged_lethal" | "fire";
export type UniformClass = "military" | "civilian" | "unknown";
export type DistanceZone = "zone_1" | "zone_2" | "zone_3";
export type ThreatLevel = "ALLY" | "OBSERVE" | "LOW" | "MEDIUM" | "HIGH" | "HUMAN_REVIEW";

export class ThreatAssessment {
  constructor(
    readonly cameraId: string,
    readonly trackId: number,
    readonly weaponType: WeaponType,
    readonly uniform: UniformClass,
    readonly zone: DistanceZone,
    readonly threatLevel: ThreatLevel,
  ) {}

  /** Human-readable label for the threat level -- the ONLY place this
   * mapping should exist; components must not stringify threatLevel
   * themselves. */
  severityLabel(): string {
    switch (this.threatLevel) {
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

  /** Returns a CSS custom-property reference, not a literal color -- stays
   * theme-controlled and reuses the prototype's existing tokens
   * (src/styles.css: --red-glow, --amber-glow, --primary, --success),
   * preserving visual parity rather than inventing a new palette. */
  displayColor(): string {
    switch (this.threatLevel) {
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

  /** Matches CLAUDE.md's Alarm Rules exactly: HIGH is alarm-eligible; FIRE
   * is immediate regardless of threat level. FIRE is a weapon_type, not a
   * threat_level, so both conditions are checked independently -- a FIRE
   * detection classified ALLY (unlikely, but not impossible pre-classification)
   * still requires immediate action per the backend's own rule precedence. */
  requiresImmediateAction(): boolean {
    return this.threatLevel === "HIGH" || this.weaponType === "fire";
  }
}
