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
from shared.schemas.alert import AlertSchema
from shared.schemas.analytics import (
    CameraAnalyticsSchema,
    IncidentAnalyticsSchema,
    SystemAnalyticsSchema,
    ThreatAnalyticsSchema,
)
from shared.schemas.api import ApiError, ApiResponse
from shared.schemas.auth import LoginRequestSchema, RefreshRequestSchema, TokenResponseSchema
from shared.schemas.calibration import (
    CalibrationStartRequestSchema,
    CalibrationValidateRequestSchema,
    CalibrationValidationResultSchema,
    ReferencePointSchema,
)
from shared.schemas.camera import (
    CameraCalibrationSchema,
    CameraConnectionStatus,
    CameraDisconnectedSchema,
    CameraHealthSchema,
    CameraSchema,
    CameraUpdateRequestSchema,
    SystemEventSchema,
)
from shared.schemas.evidence import (
    EvidenceItemSchema,
    EvidenceType,
    RecordingSchema,
    SnapshotSchema,
)
from shared.schemas.health import (
    CameraHealthSummarySchema,
    GPUHealthSchema,
    HealthStatus,
    StorageHealthSchema,
    SystemHealthSchema,
)
from shared.schemas.incident import (
    IncidentCreatedSchema,
    IncidentEventSchema,
    IncidentSchema,
    IncidentSummarySchema,
    IncidentTransitionRequestSchema,
    IncidentUpdatedSchema,
)
from shared.schemas.review import (
    RESOLUTION_STATUSES,
    HumanReviewSchema,
    ReviewResolutionRequestSchema,
    ReviewStatus,
)
from shared.schemas.threat import ActiveThreatSchema, ThreatAssessmentSchema
from shared.schemas.user import UserRoleUpdateRequestSchema, UserSchema

__all__ = [
    # analytics
    "CameraAnalyticsSchema",
    "IncidentAnalyticsSchema",
    "SystemAnalyticsSchema",
    "ThreatAnalyticsSchema",
    # api
    "ApiError",
    "ApiResponse",
    # auth
    "LoginRequestSchema",
    "RefreshRequestSchema",
    "TokenResponseSchema",
    # threat
    "ActiveThreatSchema",
    "ThreatAssessmentSchema",
    # incident
    "IncidentCreatedSchema",
    "IncidentEventSchema",
    "IncidentSchema",
    "IncidentSummarySchema",
    "IncidentTransitionRequestSchema",
    "IncidentUpdatedSchema",
    # review
    "RESOLUTION_STATUSES",
    "HumanReviewSchema",
    "ReviewResolutionRequestSchema",
    "ReviewStatus",
    # camera
    "CameraCalibrationSchema",
    "CameraConnectionStatus",
    "CameraDisconnectedSchema",
    "CameraHealthSchema",
    "CameraSchema",
    "CameraUpdateRequestSchema",
    "SystemEventSchema",
    # calibration
    "CalibrationStartRequestSchema",
    "CalibrationValidateRequestSchema",
    "CalibrationValidationResultSchema",
    "ReferencePointSchema",
    # evidence
    "EvidenceItemSchema",
    "EvidenceType",
    "RecordingSchema",
    "SnapshotSchema",
    # health
    "CameraHealthSummarySchema",
    "GPUHealthSchema",
    "HealthStatus",
    "StorageHealthSchema",
    "SystemHealthSchema",
    # alarm
    "AlarmSchema",
    # alert
    "AlertSchema",
    # user
    "UserRoleUpdateRequestSchema",
    "UserSchema",
]
