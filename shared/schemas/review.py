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
from typing import Literal

from pydantic import BaseModel

ReviewStatus = Literal["PENDING", "CONFIRMED_MILITARY", "CONFIRMED_CIVILIAN", "ESCALATED", "DISMISSED"]
"""Valid states for a human review item (ADR-023 operator actions)."""


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
    status: ReviewStatus = "PENDING"
