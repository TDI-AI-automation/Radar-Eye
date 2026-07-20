"""Shared schemas package.

Provides all API-facing Pydantic models (REST response bodies and WebSocket
message shapes) derived from docs/FRONTEND_BACKEND_CONTRACTS.md.

These are read-only response models.  For internal event payloads (used
between services on the event bus), see ``shared.events``.

Typical import patterns::

    from shared.schemas import ApiResponse, ThreatAssessmentSchema
    from shared.schemas import IncidentSchema, HumanReviewSchema
    from shared.schemas import CameraSchema, AlarmSchema
"""

from shared.schemas.alarm import AlarmSchema
from shared.schemas.api import ApiResponse
from shared.schemas.camera import CameraConnectionStatus, CameraHealthSchema, CameraSchema
from shared.schemas.incident import (
    IncidentCreatedSchema,
    IncidentSchema,
    IncidentSummarySchema,
    IncidentUpdatedSchema,
)
from shared.schemas.review import HumanReviewSchema, ReviewStatus
from shared.schemas.threat import ActiveThreatSchema, ThreatAssessmentSchema

__all__ = [
    # api
    "ApiResponse",
    # threat
    "ActiveThreatSchema",
    "ThreatAssessmentSchema",
    # incident
    "IncidentCreatedSchema",
    "IncidentSchema",
    "IncidentSummarySchema",
    "IncidentUpdatedSchema",
    # review
    "HumanReviewSchema",
    "ReviewStatus",
    # camera
    "CameraConnectionStatus",
    "CameraHealthSchema",
    "CameraSchema",
    # alarm
    "AlarmSchema",
]
