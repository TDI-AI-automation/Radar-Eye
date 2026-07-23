"""Tests for shared/constants — enum completeness and no-duplicate check.

Acceptance criteria (RM-02):
  - Every enum exists and contains exactly the values mandated by the spec.
  - No enum value string is duplicated across the canonical constant enums.
"""

from __future__ import annotations

from enum import Enum

import pytest

from shared.constants import (
    DistanceZone,
    IncidentStatus,
    IncidentType,
    ThreatLevel,
    UniformClass,
    WeaponType,
)

# ---------------------------------------------------------------------------
# ThreatLevel
# ---------------------------------------------------------------------------


class TestThreatLevel:
    def test_all_mandated_values_present(self) -> None:
        """Every level from THREAT_ENGINE_SPEC.md must exist."""
        expected = {"ALLY", "OBSERVE", "LOW", "MEDIUM", "HIGH", "HUMAN_REVIEW"}
        actual = {member.value for member in ThreatLevel}
        assert actual == expected

    def test_str_mixin(self) -> None:
        # Equality works via the str mixin on all Python versions.
        assert ThreatLevel.HIGH == "HIGH"
        # .value always returns the bare string regardless of Python version.
        assert ThreatLevel.HIGH.value == "HIGH"

    def test_member_count(self) -> None:
        assert len(ThreatLevel) == 6


# ---------------------------------------------------------------------------
# DistanceZone
# ---------------------------------------------------------------------------


class TestDistanceZone:
    def test_all_mandated_values_present(self) -> None:
        """Three zones from THREAT_ENGINE_SPEC.md."""
        expected = {"zone_1", "zone_2", "zone_3"}
        actual = {member.value for member in DistanceZone}
        assert actual == expected

    def test_str_mixin(self) -> None:
        assert DistanceZone.ZONE_1 == "zone_1"

    def test_member_count(self) -> None:
        assert len(DistanceZone) == 3


# ---------------------------------------------------------------------------
# WeaponType
# ---------------------------------------------------------------------------


class TestWeaponType:
    def test_all_mandated_values_present(self) -> None:
        """Values sourced from THREAT_ENGINE_SPEC.md detector classes (person excluded)."""
        expected = {"none", "non_lethal", "melee_lethal", "ranged_lethal", "fire"}
        actual = {member.value for member in WeaponType}
        assert actual == expected

    def test_person_not_in_weapon_type(self) -> None:
        """'person' is the tracked subject, not a weapon — must not appear."""
        values = {member.value for member in WeaponType}
        assert "person" not in values

    def test_str_mixin(self) -> None:
        assert WeaponType.RANGED_LETHAL == "ranged_lethal"

    def test_member_count(self) -> None:
        assert len(WeaponType) == 5


# ---------------------------------------------------------------------------
# UniformClass
# ---------------------------------------------------------------------------


class TestUniformClass:
    def test_all_mandated_values_present(self) -> None:
        expected = {"military", "civilian", "unknown"}
        actual = {member.value for member in UniformClass}
        assert actual == expected

    def test_str_mixin(self) -> None:
        assert UniformClass.MILITARY == "military"

    def test_member_count(self) -> None:
        assert len(UniformClass) == 3


# ---------------------------------------------------------------------------
# IncidentType
# ---------------------------------------------------------------------------


class TestIncidentType:
    def test_threat_value_present(self) -> None:
        assert IncidentType.THREAT == "THREAT"


# ---------------------------------------------------------------------------
# IncidentStatus
# ---------------------------------------------------------------------------


class TestIncidentStatus:
    def test_all_lifecycle_states_present(self) -> None:
        """Full lifecycle per docs/INCIDENT_LIFECYCLE.md: five states, not four."""
        expected = {"NEW", "ACTIVE", "ACKNOWLEDGED", "RESOLVED", "ARCHIVED"}
        actual = {member.value for member in IncidentStatus}
        assert actual == expected


# ---------------------------------------------------------------------------
# No-duplicate check across all canonical enums
# ---------------------------------------------------------------------------


class TestNoDuplicatesAcrossEnums:
    """No string value should appear in more than one canonical enum.

    This guards against future copy-paste errors introducing silent type
    confusion when comparing values from different enum families.
    """

    ENUM_CLASSES: list[type[Enum]] = [ThreatLevel, DistanceZone, WeaponType, UniformClass]

    def test_no_value_collision_across_enums(self) -> None:
        seen: dict[str, str] = {}  # value -> enum class name
        for enum_cls in self.ENUM_CLASSES:
            for member in enum_cls:
                value = member.value
                if value in seen:
                    pytest.fail(
                        f"Duplicate enum value '{value}' found in both "
                        f"{seen[value]} and {enum_cls.__name__}"
                    )
                seen[value] = enum_cls.__name__
