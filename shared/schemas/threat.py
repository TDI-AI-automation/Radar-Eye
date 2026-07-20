"""Threat-related API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md
  - "Frontend Event Models / ThreatAssessmentEvent" section
  - GET /threats/active endpoint

These models are read-only (response bodies).  They are not the internal
event payloads — see shared.events.payloads for those.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType


class ThreatAssessmentSchema(BaseModel):
    """Frontend-facing representation of a threat assessment.

    Used as the body of the ``/ws/threats`` WebSocket message and as items in
    the ``GET /threats/active`` response.

    Matches the "Frontend Event Models / ThreatAssessmentEvent" shape in
    FRONTEND_BACKEND_CONTRACTS.md (note: ``rule_id`` is omitted from the
    frontend shape per the spec).
    """

    camera_id: uuid.UUID
    track_id: int
    weapon_type: WeaponType
    uniform: UniformClass
    zone: DistanceZone
    threat_level: ThreatLevel


class ActiveThreatSchema(ThreatAssessmentSchema):
    """A currently-active threat as returned by ``GET /threats/active``.

    Extends ThreatAssessmentSchema with no additional fields for now; kept as
    a distinct type so the API can evolve (e.g. adding a ``first_seen``
    timestamp) without changing the WebSocket message shape.
    """
