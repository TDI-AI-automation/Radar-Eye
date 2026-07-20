"""Weapon type enum.

Source: docs/THREAT_ENGINE_SPEC.md — "Detector Output / Supported Classes" section.

Covers the weapon-relevant detector output classes.  The ``person`` detector
class is intentionally excluded here: it identifies the tracked subject, not
a weapon.  Use ``NONE`` when no weapon is detected on the subject.

No service may define its own WeaponType enum.
"""

from __future__ import annotations

from enum import Enum


class WeaponType(str, Enum):
    """Weapon class detected on the tracked subject by the Detection Agent."""

    NONE = "none"
    """No weapon detected.  Person only."""

    NON_LETHAL = "non_lethal"
    """Non-lethal weapon (e.g. baton, shield)."""

    MELEE_LETHAL = "melee_lethal"
    """Lethal close-quarters weapon (e.g. knife, axe)."""

    RANGED_LETHAL = "ranged_lethal"
    """Lethal ranged weapon (e.g. firearm)."""

    FIRE = "fire"
    """Fire detected.  Treated as an immediate HIGH threat regardless of zone."""
