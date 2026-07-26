"""In-memory active-threat cache -- RM-12 Phase 3 (docs/RM-12_IMPLEMENTATION_PLAN.md
Phase 3's ``/threats/active`` open design point).

The Threat Engine does not persist assessments -- it only publishes events
(docs/DATABASE_SCHEMA.md's "Transient Processing Data": per-frame threat
assessments are explicitly not stored). ``GET /threats/active`` is still a
mandatory REST contract (docs/FRONTEND_BACKEND_CONTRACTS.md's Live
Monitoring / Tactical Map sections), so it needs a real, queryable source
-- not a WS-only workaround and not fabricated data (CLAUDE.md's "avoid
mock data").

``ActiveThreatCache`` is that source: a small in-memory, TTL-based cache,
mirroring ``apps.api.app.health.HealthCollector``'s exact existing shape
(plain dict, no locking -- FastAPI's single-threaded asyncio event loop
never preempts a coroutine mid-dict-mutation, same reasoning already
established for ``HealthCollector``). It is constructed once in
``create_app()`` and stashed on ``app.state``, same pattern as
``HealthCollector``/``AuditLogger``.

Feeding it is out of scope for Phase 3 -- that requires subscribing to the
event bus, and Phase 5 is where all event-bus-subscription infrastructure
is first built (docs/RM-12_IMPLEMENTATION_PLAN.md's own stated sequencing:
"WebSocket bridge last ... no existing pattern to lean on"). Until Phase 5
wires ``EventBus.subscribe()`` to call ``record()``, ``GET /threats/active``
honestly reports zero active threats rather than being stubbed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from shared.schemas.threat import ActiveThreatSchema

DEFAULT_TTL_SECONDS = 30.0
"""How long a recorded threat assessment counts as "active" with no
follow-up update. Provisional -- revisit once Phase 5 wires a real feed and
an actual assessment-refresh cadence is observable."""


class ActiveThreatCache:
    """Tracks the most recent threat assessment per (camera_id, track_id)."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[tuple[uuid.UUID, int], tuple[ActiveThreatSchema, datetime]] = {}

    def record(self, assessment: ActiveThreatSchema, *, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(timezone.utc)
        self._entries[(assessment.camera_id, assessment.track_id)] = (assessment, timestamp)

    def get_active(self, *, now: datetime | None = None) -> list[ActiveThreatSchema]:
        """Every recorded assessment younger than the TTL, evicting expired
        entries as a side effect (same sweep-on-read pattern as
        ``HealthCollector``'s stalled-stream detection)."""
        current_time = now or datetime.now(timezone.utc)
        active: list[ActiveThreatSchema] = []
        expired_keys: list[tuple[uuid.UUID, int]] = []
        for key, (assessment, recorded_at) in self._entries.items():
            age_seconds = (current_time - recorded_at).total_seconds()
            if age_seconds > self._ttl_seconds:
                expired_keys.append(key)
            else:
                active.append(assessment)
        for key in expired_keys:
            del self._entries[key]
        return active
