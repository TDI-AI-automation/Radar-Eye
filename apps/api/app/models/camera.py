"""Camera, stream profile, and calibration tables.

Source: docs/DATABASE_SCHEMA.md -- "cameras", "camera_stream_profiles",
"camera_calibrations" sections.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, updated_at_column, uuid_pk
from shared.schemas.camera import CameraConnectionStatus, CameraLifecycleState

_CAMERA_STATUS_VALUES = get_args(CameraConnectionStatus)
_CAMERA_LIFECYCLE_VALUES = get_args(CameraLifecycleState)


class Camera(Base):
    """Registered camera source.

    Two independent state columns, per RM-12 (Camera Runtime Ownership
    Refinement / Runtime State Model) -- connection status and lifecycle
    state are orthogonal state machines, never one enum:

    - ``status`` is Observed state: written exclusively by Camera Runtime,
      reflects live RTSP connectivity. Never operator-settable via the API
      -- see routers/cameras.py's PATCH route, which deliberately excludes
      it.
    - ``lifecycle_state``, ``ai_enabled``, ``recording_enabled`` are all
      Desired/Persistent state: written exclusively by Camera Registry in
      response to an explicit operator action, independent of whether the
      camera happens to be connected right now. ``ai_enabled``/
      ``recording_enabled`` record only the operator's *intent* -- Camera
      Runtime observes them and converges toward them (attaching/detaching
      the AI branch, starting/stopping recording); this component performs
      no AI or recording behavior itself and never calls Camera Runtime.
    """

    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in _CAMERA_STATUS_VALUES)})",
            name="ck_cameras_status",
        ),
        CheckConstraint(
            f"lifecycle_state IN ({', '.join(repr(v) for v in _CAMERA_LIFECYCLE_VALUES)})",
            name="ck_cameras_lifecycle_state",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    # Provisional: Camera Registry sets this only as the required initial
    # value for a NOT NULL column at creation time (Camera Runtime doesn't
    # exist yet to supply a real observation). This is not an ownership
    # claim -- Camera Runtime's first real connection attempt overwrites it
    # as a normal write, not a correction of something Registry got wrong.
    status: Mapped[str] = mapped_column(String, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String, nullable=False, server_default="DRAFT")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    recording_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
