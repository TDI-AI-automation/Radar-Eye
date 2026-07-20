"""Uniform classification enum.

Source: docs/THREAT_ENGINE_SPEC.md — "Uniform Classification / Supported Classes" section.
Authority: Classification Agent (AGENTS.md, Agent 4).

No service may define its own UniformClass enum.
"""

from __future__ import annotations

from enum import Enum


class UniformClass(str, Enum):
    """Uniform classification assigned by the Classification Agent (ViT)."""

    MILITARY = "military"
    """Subject wearing military uniform — classified as ALLY regardless of weapon."""

    CIVILIAN = "civilian"
    """Subject wearing civilian clothing — threat level determined by weapon and zone."""

    UNKNOWN = "unknown"
    """Classification confidence too low to determine uniform type.
    Always routed to HUMAN_REVIEW; never auto-resolved.
    """
