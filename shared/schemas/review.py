"""Human review API schemas.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Threat Review Center section.
  GET /reviews, GET /reviews/{review_id}
  POST /reviews/{id}/confirm-military  etc.
Authority: ADR-023 (Human Review Workflow), AGENTS.md Agent 10.

Unknown-uniform subjects are never auto-resolved (CLAUDE.md — Human Review
Rules).  These schemas surface the queue to operators.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReviewStatus = Literal["OPEN", "CONFIRMED_MILITARY", "CONFIRMED_CIVILIAN", "ESCALATED", "DISMISSED"]
"""Valid states for a human review item (docs/DATABASE_SCHEMA.md — human_review_items
Status Values; ADR-023 operator actions)."""


class HumanReviewSchema(BaseModel):
    """Full representation of a human review queue item.

    Returned by ``GET /reviews/{review_id}`` and items in ``GET /reviews``.
    Also the body of the ``/ws/reviews`` WebSocket message
    (HumanReviewItemCreatedEvent frontend shape).
    """

    review_item_id: uuid.UUID
    camera_id: uuid.UUID
    track_id: int
    reason: str
    """Why this item was queued (e.g. "uniform_unknown")."""
    status: ReviewStatus = "OPEN"
    created_at: datetime
    """When this item was queued -- lets the Reviews screen sort the queue
    chronologically (previously absent; the DB row always had this, it
    was simply never serialized here)."""


RESOLUTION_STATUSES: tuple[ReviewStatus, ...] = (
    "CONFIRMED_MILITARY",
    "CONFIRMED_CIVILIAN",
    "ESCALATED",
    "DISMISSED",
)
"""The four allowed operator resolutions (CLAUDE.md's Human Review Rules --
Confirm Military, Confirm Civilian, Escalate, Dismiss). ``OPEN`` is never a
valid resolution target; it is the queued-and-unresolved starting state."""


class ReviewResolutionRequestSchema(BaseModel):
    """Body of ``PATCH /reviews/{review_id}`` -- the generic form of the
    four ``POST /reviews/{id}/confirm-military`` etc. convenience routes,
    which take no body (the action name fixes the target status). Both
    paths funnel through the same resolution logic -- no duplicate rules."""

    status: ReviewStatus
