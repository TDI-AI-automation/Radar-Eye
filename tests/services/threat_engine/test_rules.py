"""Exhaustive tests for the deterministic classification rule table.

Every row of docs/THREAT_ENGINE_SPEC.md's "Classification Rules" table is
tested individually, plus the fire-vs-uniform precedence decisions and full
determinism (same input -> same output, every time).
"""

from __future__ import annotations

import pytest

from services.threat_engine.rules import RuleResult, classify
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType

ALL_ZONES = [DistanceZone.ZONE_1, DistanceZone.ZONE_2, DistanceZone.ZONE_3]
ALL_WEAPONS = [
    WeaponType.NONE,
    WeaponType.NON_LETHAL,
    WeaponType.MELEE_LETHAL,
    WeaponType.RANGED_LETHAL,
    WeaponType.FIRE,
]


class TestSpecTableRows:
    """One test per literal row of THREAT_ENGINE_SPEC.md's Classification Rules table."""

    @pytest.mark.parametrize("weapon_type", ALL_WEAPONS)
    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_military_always_ally(self, weapon_type: WeaponType, zone: DistanceZone) -> None:
        result = classify(UniformClass.MILITARY, weapon_type, zone)
        if weapon_type is WeaponType.FIRE:
            assert result == RuleResult(ThreatLevel.HIGH, "FIRE_HIGH")
        else:
            assert result == RuleResult(ThreatLevel.ALLY, "MILITARY_ALLY")

    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_civilian_no_weapon_is_observe(self, zone: DistanceZone) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.NONE, zone)
        assert result == RuleResult(ThreatLevel.OBSERVE, "NO_WEAPON_OBSERVE")

    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_civilian_non_lethal_is_low(self, zone: DistanceZone) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.NON_LETHAL, zone)
        assert result == RuleResult(ThreatLevel.LOW, "NON_LETHAL_LOW")

    def test_civilian_melee_lethal_zone_3_is_low(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.MELEE_LETHAL, DistanceZone.ZONE_3)
        assert result == RuleResult(ThreatLevel.LOW, "MELEE_LETHAL_ZONE_3")

    def test_civilian_melee_lethal_zone_2_is_medium(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.MELEE_LETHAL, DistanceZone.ZONE_2)
        assert result == RuleResult(ThreatLevel.MEDIUM, "MELEE_LETHAL_ZONE_2")

    def test_civilian_melee_lethal_zone_1_is_high(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.MELEE_LETHAL, DistanceZone.ZONE_1)
        assert result == RuleResult(ThreatLevel.HIGH, "MELEE_LETHAL_ZONE_1")

    def test_civilian_ranged_lethal_zone_3_is_medium(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_3)
        assert result == RuleResult(ThreatLevel.MEDIUM, "RANGED_LETHAL_ZONE_3")

    def test_civilian_ranged_lethal_zone_2_is_high(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_2)
        assert result == RuleResult(ThreatLevel.HIGH, "RANGED_LETHAL_ZONE_2")

    def test_civilian_ranged_lethal_zone_1_is_high(self) -> None:
        result = classify(UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1)
        assert result == RuleResult(ThreatLevel.HIGH, "RANGED_LETHAL_ZONE_1")

    @pytest.mark.parametrize("weapon_type", ALL_WEAPONS)
    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_unknown_uniform_is_human_review(
        self, weapon_type: WeaponType, zone: DistanceZone
    ) -> None:
        result = classify(UniformClass.UNKNOWN, weapon_type, zone)
        if weapon_type is WeaponType.FIRE:
            assert result == RuleResult(ThreatLevel.HIGH, "FIRE_HIGH")
        else:
            assert result == RuleResult(ThreatLevel.HUMAN_REVIEW, "UNKNOWN_UNIFORM_HUMAN_REVIEW")

    @pytest.mark.parametrize(
        "uniform", [UniformClass.MILITARY, UniformClass.CIVILIAN, UniformClass.UNKNOWN]
    )
    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_fire_is_always_high(self, uniform: UniformClass, zone: DistanceZone) -> None:
        result = classify(uniform, WeaponType.FIRE, zone)
        assert result == RuleResult(ThreatLevel.HIGH, "FIRE_HIGH")


class TestPrecedence:
    """Confirms the explicitly resolved precedence: FIRE > UNKNOWN/MILITARY uniform overrides."""

    def test_fire_overrides_military_ally(self) -> None:
        result = classify(UniformClass.MILITARY, WeaponType.FIRE, DistanceZone.ZONE_3)
        assert result.threat_level is ThreatLevel.HIGH
        assert result.rule_id == "FIRE_HIGH"

    def test_fire_overrides_unknown_human_review(self) -> None:
        result = classify(UniformClass.UNKNOWN, WeaponType.FIRE, DistanceZone.ZONE_1)
        assert result.threat_level is ThreatLevel.HIGH
        assert result.rule_id == "FIRE_HIGH"


class TestDeterminism:
    """Identical inputs must always produce identical outputs."""

    @pytest.mark.parametrize(
        "uniform", [UniformClass.MILITARY, UniformClass.CIVILIAN, UniformClass.UNKNOWN]
    )
    @pytest.mark.parametrize("weapon_type", ALL_WEAPONS)
    @pytest.mark.parametrize("zone", ALL_ZONES)
    def test_repeated_calls_are_identical(
        self, uniform: UniformClass, weapon_type: WeaponType, zone: DistanceZone
    ) -> None:
        results = [classify(uniform, weapon_type, zone) for _ in range(5)]
        assert len(set(results)) == 1

    def test_every_combination_returns_a_result(self) -> None:
        for uniform in UniformClass:
            for weapon_type in ALL_WEAPONS:
                for zone in ALL_ZONES:
                    result = classify(uniform, weapon_type, zone)
                    assert isinstance(result, RuleResult)
                    assert isinstance(result.rule_id, str) and result.rule_id
