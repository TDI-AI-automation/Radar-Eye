"""Threat Engine — deterministic rule-based threat evaluation.

Source: docs/THREAT_ENGINE_SPEC.md. Authority: ADR-015.
"""

from __future__ import annotations

from services.threat_engine.engine import ThreatEngine
from services.threat_engine.rules import RuleResult, classify
from services.threat_engine.types import EscalationSignal, EscalationSignalType

__all__ = [
    "EscalationSignal",
    "EscalationSignalType",
    "RuleResult",
    "ThreatEngine",
    "classify",
]
