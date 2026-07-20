"""Thin persistence adapters -- one repository per ORM model.

See apps.api.app.repositories.base.Repository. Repositories perform
persistence operations only; business logic belongs to the service that
calls them.
"""

from __future__ import annotations

from apps.api.app.repositories.base import Repository
from apps.api.app.repositories.camera import (
    CameraCalibrationRepository,
    CameraRepository,
    CameraStreamProfileRepository,
)
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.repositories.incident import IncidentEventRepository, IncidentRepository
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from apps.api.app.repositories.system_event import SystemEventRepository
from apps.api.app.repositories.user import UserRepository

__all__ = [
    "CameraCalibrationRepository",
    "CameraRepository",
    "CameraStreamProfileRepository",
    "HumanReviewRepository",
    "IncidentEventRepository",
    "IncidentRepository",
    "RecordingRepository",
    "Repository",
    "SnapshotRepository",
    "SystemEventRepository",
    "UserRepository",
]
