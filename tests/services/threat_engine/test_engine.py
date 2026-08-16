"""Tests for the per-track escalation / de-escalation state machine.

Source: docs/THREAT_ENGINE_SPEC.md — "Threat Escalation Policy" and
"Threat De-escalation Policy". All timestamps are synthetic and supplied
explicitly, per the engine's determinism requirement -- no wall-clock reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from services.threat_engine.engine import ThreatEngine
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.types import HumanReviewItemCreatedEvent, ThreatAssessmentEvent

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _ingest(engine, camera_id, track_id, uniform, weapon_type, zone, seconds):
    return engine.ingest(
        camera_id=camera_id,
        track_id=track_id,
        uniform=uniform,
        weapon_type=weapon_type,
        zone=zone,
        timestamp=_t(seconds),
    )


class TestHighEscalationDebounceAndTimers:
    def test_high_requires_three_consecutive_frames_before_reporting(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.RANGED_LETHAL,
            DistanceZone.ZONE_1,
            0.0,
        )
        assert events == []

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.RANGED_LETHAL,
            DistanceZone.ZONE_1,
            0.1,
        )
        assert events == []

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.RANGED_LETHAL,
            DistanceZone.ZONE_1,
            0.2,
        )
        assert len(events) == 1
        assert type(events[0]) is ThreatAssessmentEvent
        assert events[0].payload.threat_level is ThreatLevel.HIGH
        assert events[0].payload.rule_id == "RANGED_LETHAL_ZONE_1"

    def test_high_full_lifecycle_incident_alarm_then_deescalation(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_high = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1)

        # Confirm HIGH at t=0.2 (3rd consecutive frame).
        _ingest(engine, camera_id, track_id, *civilian_high, 0.0)
        _ingest(engine, camera_id, track_id, *civilian_high, 0.1)
        events = _ingest(engine, camera_id, track_id, *civilian_high, 0.2)
        assert [type(e) for e in events] == [ThreatAssessmentEvent]

        # 1.1s after confirmation -> INCIDENT_ELIGIBLE.
        events = _ingest(engine, camera_id, track_id, *civilian_high, 1.3)
        signals = [e for e in events if isinstance(e, EscalationSignal)]
        assert len(signals) == 1
        assert signals[0].signal_type is EscalationSignalType.INCIDENT_ELIGIBLE
        assert signals[0].threat_level is ThreatLevel.HIGH

        # 3.1s after confirmation -> ALARM_ELIGIBLE (incident not re-signaled).
        events = _ingest(engine, camera_id, track_id, *civilian_high, 3.3)
        signals = [e for e in events if isinstance(e, EscalationSignal)]
        assert len(signals) == 1
        assert signals[0].signal_type is EscalationSignalType.ALARM_ELIGIBLE

        # Threat disappears (civilian, no weapon -> OBSERVE). Within the 10s
        # HIGH de-escalation window, the engine keeps reporting the held HIGH
        # conditions and does not re-signal (already signaled).
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            4.3,
        )
        assert len(events) == 1
        assert type(events[0]) is ThreatAssessmentEvent
        assert events[0].payload.threat_level is ThreatLevel.HIGH
        assert events[0].payload.rule_id == "RANGED_LETHAL_ZONE_1"

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            14.2,
        )
        assert len(events) == 1
        assert events[0].payload.threat_level is ThreatLevel.HIGH  # still holding, 9.9s < 10s

        # 10.1s of continuous absence -> downgrades to the current raw level.
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            14.4,
        )
        assert len(events) == 1
        assert type(events[0]) is ThreatAssessmentEvent
        assert events[0].payload.threat_level is ThreatLevel.OBSERVE
        assert events[0].payload.rule_id == "NO_WEAPON_OBSERVE"

    def test_high_deescalation_resets_if_threat_reappears(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_high = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1)

        _ingest(engine, camera_id, track_id, *civilian_high, 0.0)
        _ingest(engine, camera_id, track_id, *civilian_high, 0.1)
        _ingest(engine, camera_id, track_id, *civilian_high, 0.2)

        # Absent for 8s (below the 10s threshold)...
        _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            8.2,
        )
        # ...then HIGH reappears before downgrade -- still confirmed HIGH, no debounce needed again.
        events = _ingest(engine, camera_id, track_id, *civilian_high, 8.3)
        assert len(events) == 1
        assert events[0].payload.threat_level is ThreatLevel.HIGH

        # Now absence must restart from scratch: 9.9s later (< 10s) still holds.
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            18.1,
        )
        assert events[0].payload.threat_level is ThreatLevel.HIGH


class TestMediumEscalation:
    def test_medium_reports_immediately_no_debounce(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.RANGED_LETHAL,
            DistanceZone.ZONE_3,
            0.0,
        )
        assert len(events) == 1
        assert events[0].payload.threat_level is ThreatLevel.MEDIUM

    def test_medium_sustained_two_seconds_triggers_incident_never_alarm(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_medium = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_3)

        _ingest(engine, camera_id, track_id, *civilian_medium, 0.0)
        events = _ingest(engine, camera_id, track_id, *civilian_medium, 2.1)
        signals = [e for e in events if isinstance(e, EscalationSignal)]
        assert len(signals) == 1
        assert signals[0].signal_type is EscalationSignalType.INCIDENT_ELIGIBLE

        # Even far beyond the alarm-eligible window, MEDIUM never alarms (ADR-026).
        events = _ingest(engine, camera_id, track_id, *civilian_medium, 20.0)
        signals = [e for e in events if isinstance(e, EscalationSignal)]
        assert signals == []

    def test_medium_deescalates_after_five_seconds_absence(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_medium = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_3)

        _ingest(engine, camera_id, track_id, *civilian_medium, 0.0)
        _ingest(engine, camera_id, track_id, *civilian_medium, 2.1)  # incident signaled

        # Absence clock starts at the first below-threshold frame (t=4.9), not
        # at the original confirmation.
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_3,
            4.9,
        )
        assert events[0].payload.threat_level is ThreatLevel.MEDIUM

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_3,
            9.8,
        )
        assert events[0].payload.threat_level is ThreatLevel.MEDIUM  # 4.9s absence < 5s, still held

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_3,
            10.0,
        )
        assert events[0].payload.threat_level is ThreatLevel.OBSERVE  # 5.1s absence >= 5s


class TestLowEscalation:
    def test_low_never_signals_incident_or_alarm(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_low = (UniformClass.CIVILIAN, WeaponType.NON_LETHAL, DistanceZone.ZONE_1)

        for seconds in (0.0, 5.0, 50.0):
            events = _ingest(engine, camera_id, track_id, *civilian_low, seconds)
            assert [e for e in events if isinstance(e, EscalationSignal)] == []

    def test_low_deescalates_after_three_seconds_absence(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_low = (UniformClass.CIVILIAN, WeaponType.NON_LETHAL, DistanceZone.ZONE_1)

        _ingest(engine, camera_id, track_id, *civilian_low, 0.0)

        # Absence clock starts at the first below-threshold frame (t=0.5).
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            0.5,
        )
        assert events[0].payload.threat_level is ThreatLevel.LOW

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            3.4,
        )
        assert events[0].payload.threat_level is ThreatLevel.LOW  # 2.9s absence < 3s, still held

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_1,
            3.6,
        )
        assert events[0].payload.threat_level is ThreatLevel.OBSERVE  # 3.1s absence >= 3s


class TestFire:
    def test_fire_is_immediate_no_waiting_period(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1

        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.FIRE,
            DistanceZone.ZONE_2,
            0.0,
        )

        assert len(events) == 3
        threat_events = [e for e in events if type(e) is ThreatAssessmentEvent]
        signals = [e for e in events if isinstance(e, EscalationSignal)]
        assert len(threat_events) == 1
        assert threat_events[0].payload.threat_level is ThreatLevel.HIGH
        assert threat_events[0].payload.rule_id == "FIRE_HIGH"
        assert {s.signal_type for s in signals} == {
            EscalationSignalType.INCIDENT_ELIGIBLE,
            EscalationSignalType.ALARM_ELIGIBLE,
        }

    def test_fire_not_resignaled_on_subsequent_frames(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1

        _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.FIRE,
            DistanceZone.ZONE_2,
            0.0,
        )
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.FIRE,
            DistanceZone.ZONE_2,
            0.5,
        )

        assert len(events) == 1
        assert type(events[0]) is ThreatAssessmentEvent

    def test_fire_resignals_after_track_reset(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1

        _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.FIRE,
            DistanceZone.ZONE_2,
            0.0,
        )
        engine.reset_track(camera_id, track_id)
        events = _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.FIRE,
            DistanceZone.ZONE_2,
            1.0,
        )

        assert len(events) == 3


class TestHumanReview:
    def test_human_review_item_created_once_per_episode(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        unknown = (UniformClass.UNKNOWN, WeaponType.NONE, DistanceZone.ZONE_2)

        events = _ingest(engine, camera_id, track_id, *unknown, 0.0)
        assert [type(e) for e in events] == [ThreatAssessmentEvent, HumanReviewItemCreatedEvent]
        assert events[0].payload.threat_level is ThreatLevel.HUMAN_REVIEW
        review_item_id = events[1].payload.review_item_id

        # Same episode continues: no second HumanReviewItemCreatedEvent.
        events = _ingest(engine, camera_id, track_id, *unknown, 1.0)
        assert [type(e) for e in events] == [ThreatAssessmentEvent]

        # New episode (uniform resolves then goes unknown again) -> a new review item.
        _ingest(
            engine,
            camera_id,
            track_id,
            UniformClass.CIVILIAN,
            WeaponType.NONE,
            DistanceZone.ZONE_2,
            2.0,
        )
        events = _ingest(engine, camera_id, track_id, *unknown, 3.0)
        assert [type(e) for e in events] == [ThreatAssessmentEvent, HumanReviewItemCreatedEvent]
        assert events[1].payload.review_item_id != review_item_id


class TestTrackIsolation:
    def test_different_tracks_have_independent_state(self) -> None:
        engine = ThreatEngine()
        camera_id = uuid.uuid4()
        civilian_high = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1)

        _ingest(engine, camera_id, 1, *civilian_high, 0.0)
        _ingest(engine, camera_id, 1, *civilian_high, 0.1)
        _ingest(engine, camera_id, 1, *civilian_high, 0.2)  # track 1 confirmed HIGH

        events = _ingest(engine, camera_id, 2, *civilian_high, 0.2)  # track 2, first frame
        assert events == []  # not yet confirmed for track 2 -- independent streak

    def test_reset_track_clears_state(self) -> None:
        engine = ThreatEngine()
        camera_id, track_id = uuid.uuid4(), 1
        civilian_high = (UniformClass.CIVILIAN, WeaponType.RANGED_LETHAL, DistanceZone.ZONE_1)

        _ingest(engine, camera_id, track_id, *civilian_high, 0.0)
        _ingest(engine, camera_id, track_id, *civilian_high, 0.1)
        _ingest(engine, camera_id, track_id, *civilian_high, 0.2)  # confirmed HIGH

        engine.reset_track(camera_id, track_id)

        events = _ingest(engine, camera_id, track_id, *civilian_high, 0.3)
        assert events == []  # streak restarted from zero
