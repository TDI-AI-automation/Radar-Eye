"""Deterministic threat classification rule table.

Source: docs/THREAT_ENGINE_SPEC.md — "Classification Rules" section.
Authority: ADR-015 (Threat Engine Architecture).

``classify`` is a pure function: identical (uniform, weapon_type, zone) input
always produces identical output. No probabilistic or AI-generated logic is
permitted here (THREAT_ENGINE_SPEC.md — "Determinism Requirement").

Rule precedence (highest first) — fire is a hazard-detection signal
independent of uniform, so it is evaluated before uniform-based overrides:
  1. weapon_type == FIRE           -> HIGH, regardless of uniform or zone.
  2. uniform == UNKNOWN            -> HUMAN_REVIEW, regardless of weapon or zone.
  3. uniform == MILITARY           -> ALLY, regardless of weapon or zone.
  4. civilian: weapon/zone lookup table below.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType


@dataclass(frozen=True)
class RuleResult:
    """Outcome of a single classification decision."""

    threat_level: ThreatLevel
    rule_id: str


_FIRE_RESULT = RuleResult(ThreatLevel.HIGH, "FIRE_HIGH")
_MILITARY_RESULT = RuleResult(ThreatLevel.ALLY, "MILITARY_ALLY")
_UNKNOWN_RESULT = RuleResult(ThreatLevel.HUMAN_REVIEW, "UNKNOWN_UNIFORM_HUMAN_REVIEW")
_NO_WEAPON_RESULT = RuleResult(ThreatLevel.OBSERVE, "NO_WEAPON_OBSERVE")
_NON_LETHAL_RESULT = RuleResult(ThreatLevel.LOW, "NON_LETHAL_LOW")

# Civilian weapon/zone lookup — every row of THREAT_ENGINE_SPEC.md's table
# for melee_lethal and ranged_lethal weapons.
_CIVILIAN_WEAPON_ZONE_TABLE: dict[tuple[WeaponType, DistanceZone], RuleResult] = {
    (WeaponType.MELEE_LETHAL, DistanceZone.ZONE_3): RuleResult(
        ThreatLevel.LOW, "MELEE_LETHAL_ZONE_3"
    ),
    (WeaponType.MELEE_LETHAL, DistanceZone.ZONE_2): RuleResult(
        ThreatLevel.MEDIUM, "MELEE_LETHAL_ZONE_2"
    ),
    (WeaponType.MELEE_LETHAL, DistanceZone.ZONE_1): RuleResult(
        ThreatLevel.HIGH, "MELEE_LETHAL_ZONE_1"
    ),
    (WeaponType.RANGED_LETHAL, DistanceZone.ZONE_3): RuleResult(
        ThreatLevel.MEDIUM, "RANGED_LETHAL_ZONE_3"
    ),
    (WeaponType.RANGED_LETHAL, DistanceZone.ZONE_2): RuleResult(
        ThreatLevel.HIGH, "RANGED_LETHAL_ZONE_2"
    ),
    (WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1): RuleResult(
        ThreatLevel.HIGH, "RANGED_LETHAL_ZONE_1"
    ),
}


def classify(uniform: UniformClass, weapon_type: WeaponType, zone: DistanceZone) -> RuleResult:
    """Deterministically classify a tracked subject into a threat level.

    Precedence: FIRE overrides uniform; UNKNOWN uniform overrides weapon/zone;
    MILITARY uniform overrides weapon/zone; otherwise the civilian weapon/zone
    table applies.
    """
    if weapon_type is WeaponType.FIRE:
        return _FIRE_RESULT

    if uniform is UniformClass.UNKNOWN:
        return _UNKNOWN_RESULT

    if uniform is UniformClass.MILITARY:
        return _MILITARY_RESULT

    if weapon_type is WeaponType.NONE:
        return _NO_WEAPON_RESULT

    if weapon_type is WeaponType.NON_LETHAL:
        return _NON_LETHAL_RESULT

    return _CIVILIAN_WEAPON_ZONE_TABLE[(weapon_type, zone)]
