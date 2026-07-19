"""Generic event envelope.

Source: docs/EVENT_CONTRACTS.md — "Event Envelope" section.

Every internal Radar Eye event is wrapped in this envelope.  The envelope
is immutable (frozen Pydantic model) — events must never be modified after
publication (EVENT_CONTRACTS.md — "Event Transport Rules").

Usage::

    from shared.events.envelope import EventEnvelope
    from shared.events.payloads import ThreatAssessmentPayload

    event = EventEnvelope[ThreatAssessmentPayload](
        event_type="ThreatAssessmentEvent",
        source="threat_engine",
        payload=ThreatAssessmentPayload(...),
    )
    json_str = event.model_dump_json()
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

P = TypeVar("P", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[P]):
    """Versioned, immutable wrapper for all internal Radar Eye events.

    Fields mirror the mandatory envelope structure in EVENT_CONTRACTS.md:
      - event_id       : unique identifier for this event instance
      - schema_version : incremented on breaking payload changes
      - event_type     : string name of the event (e.g. "ThreatAssessmentEvent")
      - source         : originating component (e.g. "threat_engine")
      - timestamp      : UTC time of event creation
      - payload        : typed event-specific data
    """

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    schema_version: int = Field(default=1, ge=1)
    event_type: str
    source: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    payload: P
