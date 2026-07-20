"""Threat level enum.

Source: docs/THREAT_ENGINE_SPEC.md — "Threat Levels" section.
Authority: ADR-015 (Threat Engine Architecture).

Defines the complete set of outcomes the Threat Engine may assign to a
tracked subject.  No service may define its own ThreatLevel enum.
"""

from __future__ import annotations

from enum import Enum


class ThreatLevel(str, Enum):
    """Operational threat classification assigned by the Threat Engine."""

    ALLY = "ALLY"
    """Subject identified as military — no threat."""

    OBSERVE = "OBSERVE"
    """Civilian, no weapon present — monitor only."""

    LOW = "LOW"
    """Civilian with non-lethal weapon, or melee weapon at long range."""

    MEDIUM = "MEDIUM"
    """Elevated risk; incident created after 2-second persistence."""

    HIGH = "HIGH"
    """Immediate threat; incident created after 1 second, alarm after 3 seconds."""

    HUMAN_REVIEW = "HUMAN_REVIEW"
    """Uniform classification unknown — operator action required."""
