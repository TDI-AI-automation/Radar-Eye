"""Human review queue table.

Source: docs/DATABASE_SCHEMA.md -- "human_review_items" section.
Authority: ADR-023 (Human Review Workflow).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models.base import Base, created_at_column, uuid_pk
from shared.schemas.review import ReviewStatus

_REVIEW_STATUS_VALUES = get_args(ReviewStatus)


class HumanReviewItem(Base):
    """A threat requiring operator review (uniform classification == unknown)."""

    __tablename__ = "human_review_items"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in _REVIEW_STATUS_VALUES)})",
            name="ck_human_review_items_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN", index=True)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
