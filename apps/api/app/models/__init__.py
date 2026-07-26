"""SQLAlchemy ORM models -- one module per docs/DATABASE_SCHEMA.md table group.

Every model must be imported here so ``Base.metadata`` (used by Alembic's
autogenerate and by tests that create/drop the schema) sees the complete set
of tables.
"""

from __future__ import annotations

from apps.api.app.models.audit_log import AuditLog
from apps.api.app.models.base import Base
from apps.api.app.models.camera import Camera, CameraCalibration, CameraStreamProfile
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.models.incident import Incident, IncidentEvent
from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.models.system_event import SystemEvent
from apps.api.app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Camera",
    "CameraCalibration",
    "CameraStreamProfile",
    "HumanReviewItem",
    "Incident",
    "IncidentEvent",
    "Recording",
    "Snapshot",
    "SystemEvent",
    "User",
]
