"""Distance zone enum.

Source: docs/THREAT_ENGINE_SPEC.md — "Distance Zones" section.
Authority: ADR-016 (Distance Estimation Strategy).

Zone boundaries (ground-plane projection):
  ZONE_1 — 0 m to 20 m
  ZONE_2 — 20 m to 50 m
  ZONE_3 — 50 m+

No service may define its own DistanceZone enum.
"""

from __future__ import annotations

from enum import Enum


class DistanceZone(str, Enum):
    """Ground-plane distance zone assigned by the Distance Estimation Agent."""

    ZONE_1 = "zone_1"
    """0 m – 20 m.  Closest zone; highest lethality risk."""

    ZONE_2 = "zone_2"
    """20 m – 50 m.  Intermediate zone."""

    ZONE_3 = "zone_3"
    """50 m+.  Far zone; reduced immediate risk."""
