"""Camera, stream profile, and calibration tables.

Source: docs/DATABASE_SCHEMA.md -- "cameras", "camera_stream_profiles",
"camera_calibrations" sections.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, updated_at_column, uuid_pk
from shared.schemas.camera import CameraConnectionStatus

_CAMERA_STATUS_VALUES = get_args(CameraConnectionStatus)


class Camera(Base):
    """Registered camera source.

    Status values match shared.schemas.camera.CameraConnectionStatus.
    """

    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in _CAMERA_STATUS_VALUES)})",
            name="ck_cameras_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class CameraStreamProfile(Base):
    """Camera connection configuration. ``rtsp_url_encrypted`` is opaque
    ciphertext -- see apps.api.app.security.encryption.CredentialEncryptionProvider.
    """

    __tablename__ = "camera_stream_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    rtsp_url_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    transport: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class CameraCalibration(Base):
    """Calibration data for ground-plane distance estimation (ADR-016)."""

    __tablename__ = "camera_calibrations"

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    homography_matrix: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reference_points: Mapped[dict] = mapped_column(JSONB, nullable=False)
    calibrated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
