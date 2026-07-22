"""Per-track escalation / de-escalation state machine.

Source: docs/THREAT_ENGINE_SPEC.md — "Threat Escalation Policy" and
"Threat De-escalation Policy" sections. Authority: ADR-021, ADR-022.

``ThreatEngine`` is a pure, in-memory decision engine (ADR-008 — no
frames/detections/tracks persisted to the database). Callers supply an
explicit ``timestamp`` per classified frame rather than the engine reading
wall-clock time, so behavior stays deterministic and testable with synthetic
input (THREAT_ENGINE_SPEC.md — "Determinism Requirement").

Design notes:
  - Only HIGH requires 3 consecutive raw frames before it is confirmed and
    reported. Every other level (ALLY/OBSERVE/LOW/MEDIUM/HUMAN_REVIEW) is
    reported immediately from the current frame's own classification.
  - While a track is confirmed at HIGH/MEDIUM/LOW and the raw classification
    drops below that level, the engine holds the prior confirmed level (and
    keeps reporting the conditions that produced it) until the de-escalation
    window elapses, to prevent flicker. ALLY/OBSERVE/HUMAN_REVIEW have no
    de-escalation window (not specified in the spec) and transition
    immediately.
  - FIRE bypasses all debounce/timers: immediate ThreatAssessmentEvent plus
    both escalation signals, on the first FIRE frame only per episode.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from services.threat_engine.rules import RuleResult, classify
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.payloads import HumanReviewItemCreatedPayload, ThreatAssessmentPayload
from shared.events.types import HumanReviewItemCreatedEvent, ThreatAssessmentEvent

_HIGH_CONFIRM_FRAMES = 3

_DEESCALATION_SECONDS: dict[ThreatLevel, float] = {
    ThreatLevel.HIGH: 10.0,
    ThreatLevel.MEDIUM: 5.0,
    ThreatLevel.LOW: 3.0,
}
_INCIDENT_SECONDS: dict[ThreatLevel, float] = {
    ThreatLevel.HIGH: 1.0,
    ThreatLevel.MEDIUM: 2.0,
}
_ALARM_SECONDS: dict[ThreatLevel, float] = {
    ThreatLevel.HIGH: 3.0,
}
_SEVERITY_RANK: dict[ThreatLevel, int] = {
    ThreatLevel.HIGH: 3,
    ThreatLevel.MEDIUM: 2,
    ThreatLevel.LOW: 1,
}

TrackKey = tuple[uuid.UUID, int]


@dataclass
class _TrackState:
    level: ThreatLevel | None = None
    rule_id: str | None = None
    weapon_type: WeaponType | None = None
    uniform: UniformClass | None = None
    zone: DistanceZone | None = None
    since: datetime | None = None
    high_streak: int = 0
    below_since: datetime | None = None
    incident_signaled: bool = False
    alarm_signaled: bool = False
    review_signaled: bool = False


IngestResult = list[ThreatAssessmentEvent | HumanReviewItemCreatedEvent | EscalationSignal]


class ThreatEngine:
    """Tracks per-(camera_id, track_id) escalation state and emits decisions."""

    def __init__(self) -> None:
        self._tracks: dict[TrackKey, _TrackState] = {}

    def reset_track(self, camera_id: uuid.UUID, track_id: int) -> None:
        """Drop all state for a track (e.g. once it is reported lost/closed)."""
        self._tracks.pop((camera_id, track_id), None)

    def ingest(
        self,
        *,
        camera_id: uuid.UUID,
        track_id: int,
        uniform: UniformClass,
        weapon_type: WeaponType,
        zone: DistanceZone,
        timestamp: datetime,
    ) -> IngestResult:
        """Classify one frame for a track and advance its escalation state."""
        result = classify(uniform, weapon_type, zone)

        if weapon_type is WeaponType.FIRE:
            return self._ingest_fire(camera_id, track_id, uniform, zone, result, timestamp)

        key = (camera_id, track_id)
        state = self._tracks.setdefault(key, _TrackState())
        events: IngestResult = []

        if result.threat_level is ThreatLevel.HIGH:
            state.below_since = None
            if state.level is ThreatLevel.HIGH:
                self._confirm(
                    state, result, uniform, weapon_type, zone, timestamp, reset_since=False
                )
                events.append(self._threat_event(camera_id, track_id, state, timestamp))
                events.extend(self._check_timers(camera_id, track_id, state, timestamp))
                return events

            state.high_streak += 1
            if state.high_streak < _HIGH_CONFIRM_FRAMES:
                return events

            self._confirm(state, result, uniform, weapon_type, zone, timestamp, reset_since=True)
            events.append(self._threat_event(camera_id, track_id, state, timestamp))
            events.extend(self._check_timers(camera_id, track_id, state, timestamp))
            return events

        state.high_streak = 0

        if state.level is None:
            self._confirm(state, result, uniform, weapon_type, zone, timestamp, reset_since=True)
            events.append(self._threat_event(camera_id, track_id, state, timestamp))
            self._maybe_review(camera_id, track_id, state, timestamp, events)
            events.extend(self._check_timers(camera_id, track_id, state, timestamp))
            return events

        if result.threat_level == state.level:
            state.below_since = None
            self._confirm(state, result, uniform, weapon_type, zone, timestamp, reset_since=False)
            events.append(self._threat_event(camera_id, track_id, state, timestamp))
            self._maybe_review(camera_id, track_id, state, timestamp, events)
            events.extend(self._check_timers(camera_id, track_id, state, timestamp))
            return events

        is_downgrade = (
            state.level in _DEESCALATION_SECONDS
            and _SEVERITY_RANK.get(result.threat_level, 0) < _SEVERITY_RANK[state.level]
        )
        if not is_downgrade:
            self._confirm(state, result, uniform, weapon_type, zone, timestamp, reset_since=True)
            events.append(self._threat_event(camera_id, track_id, state, timestamp))
            self._maybe_review(camera_id, track_id, state, timestamp, events)
            events.extend(self._check_timers(camera_id, track_id, state, timestamp))
            return events

        if state.below_since is None:
            state.below_since = timestamp
        elapsed = (timestamp - state.below_since).total_seconds()
        threshold = _DEESCALATION_SECONDS[state.level]
        if elapsed < threshold:
            events.append(self._threat_event(camera_id, track_id, state, timestamp))
            events.extend(self._check_timers(camera_id, track_id, state, timestamp))
            return events

        state.below_since = None
        self._confirm(state, result, uniform, weapon_type, zone, timestamp, reset_since=True)
        events.append(self._threat_event(camera_id, track_id, state, timestamp))
        self._maybe_review(camera_id, track_id, state, timestamp, events)
        events.extend(self._check_timers(camera_id, track_id, state, timestamp))
        return events

    def _ingest_fire(
        self,
        camera_id: uuid.UUID,
        track_id: int,
        uniform: UniformClass,
        zone: DistanceZone,
        result: RuleResult,
        timestamp: datetime,
    ) -> IngestResult:
        key = (camera_id, track_id)
        state = self._tracks.get(key)
        already_active = (
            state is not None
            and state.level is ThreatLevel.HIGH
            and state.rule_id == result.rule_id
        )

        state = state or _TrackState()
        state.level = result.threat_level
        state.rule_id = result.rule_id
        state.weapon_type = WeaponType.FIRE
        state.uniform = uniform
        state.zone = zone
        state.since = state.since if already_active else timestamp
        state.high_streak = _HIGH_CONFIRM_FRAMES
        state.below_since = None
        self._tracks[key] = state

        events: IngestResult = [self._threat_event(camera_id, track_id, state, timestamp)]
        if not already_active:
            state.incident_signaled = True
            state.alarm_signaled = True
            events.append(
                EscalationSignal(
                    camera_id,
                    track_id,
                    EscalationSignalType.INCIDENT_ELIGIBLE,
                    ThreatLevel.HIGH,
                    "fire_detected",
                )
            )
            events.append(
                EscalationSignal(
                    camera_id,
                    track_id,
                    EscalationSignalType.ALARM_ELIGIBLE,
                    ThreatLevel.HIGH,
                    "fire_detected",
                )
            )
        return events

    @staticmethod
    def _confirm(
        state: _TrackState,
        result: RuleResult,
        uniform: UniformClass,
        weapon_type: WeaponType,
        zone: DistanceZone,
        timestamp: datetime,
        *,
        reset_since: bool,
    ) -> None:
        state.level = result.threat_level
        state.rule_id = result.rule_id
        state.weapon_type = weapon_type
        state.uniform = uniform
        state.zone = zone
        if reset_since:
            state.since = timestamp
            state.incident_signaled = False
            state.alarm_signaled = False
            state.review_signaled = False

    @staticmethod
    def _threat_event(
        camera_id: uuid.UUID, track_id: int, state: _TrackState, timestamp: datetime
    ) -> ThreatAssessmentEvent:
        assert state.level is not None and state.rule_id is not None
        assert (
            state.weapon_type is not None and state.uniform is not None and state.zone is not None
        )
        return ThreatAssessmentEvent(
            event_type="ThreatAssessmentEvent",
            source="threat_engine",
            timestamp=timestamp,
            payload=ThreatAssessmentPayload(
                camera_id=camera_id,
                track_id=track_id,
                weapon_type=state.weapon_type,
                uniform=state.uniform,
                zone=state.zone,
                threat_level=state.level,
                rule_id=state.rule_id,
            ),
        )

    @staticmethod
    def _maybe_review(
        camera_id: uuid.UUID,
        track_id: int,
        state: _TrackState,
        timestamp: datetime,
        events: IngestResult,
    ) -> None:
        if state.level is ThreatLevel.HUMAN_REVIEW and not state.review_signaled:
            state.review_signaled = True
            events.append(
                HumanReviewItemCreatedEvent(
                    event_type="HumanReviewItemCreatedEvent",
                    source="threat_engine",
                    timestamp=timestamp,
                    payload=HumanReviewItemCreatedPayload(
                        camera_id=camera_id,
                        track_id=track_id,
                        reason="uniform_unknown",
                        review_item_id=uuid.uuid4(),
                    ),
                )
            )

    @staticmethod
    def _check_timers(
        camera_id: uuid.UUID, track_id: int, state: _TrackState, timestamp: datetime
    ) -> IngestResult:
        assert state.level is not None and state.since is not None
        events: IngestResult = []
        elapsed = (timestamp - state.since).total_seconds()

        incident_threshold = _INCIDENT_SECONDS.get(state.level)
        if (
            incident_threshold is not None
            and elapsed >= incident_threshold
            and not state.incident_signaled
        ):
            state.incident_signaled = True
            events.append(
                EscalationSignal(
                    camera_id,
                    track_id,
                    EscalationSignalType.INCIDENT_ELIGIBLE,
                    state.level,
                    f"sustained_{state.level.value.lower()}_threat",
                )
            )

        alarm_threshold = _ALARM_SECONDS.get(state.level)
        if alarm_threshold is not None and elapsed >= alarm_threshold and not state.alarm_signaled:
            state.alarm_signaled = True
            events.append(
                EscalationSignal(
                    camera_id,
                    track_id,
                    EscalationSignalType.ALARM_ELIGIBLE,
                    state.level,
                    "sustained_high_threat",
                )
            )

        return events


__all__ = ["ThreatEngine", "EscalationSignal", "EscalationSignalType"]
