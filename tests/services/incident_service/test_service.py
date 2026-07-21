"""Tests for services.incident_service.service.IncidentService.

Source: docs/IMPLEMENTATION_ROADMAP.md's RM-07 acceptance criteria (exactly
one incident per track, never duplicates; 10s track-lost auto-close) plus
the RM-07 design review's decisions (handle_escalation() contains no
escalation-timing logic; real PostgreSQL required -- no SQLite substitution,
per RM-03's testing policy, carried forward here since this exercises the
same dedup constraint).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from apps.api.app.models.camera import Camera
from apps.api.app.models.incident import Incident
from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.incident import IncidentRepository
from services.incident_service.service import TRACK_LOST_SECONDS, IncidentService
from shared.constants.distance_zones import DistanceZone
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.bus import InProcessEventBus
from shared.events.payloads import ThreatAssessmentPayload
from shared.events.types import ThreatAssessmentEvent

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _make_camera(session) -> Camera:
    camera = Camera(name="cam-1", status="CONNECTED")
    return await CameraRepository(session).add(camera)


def _collecting_handler(sink: list):
    async def handler(event):
        sink.append(event)

    return handler


def _threat_assessment(
    camera_id: uuid.UUID, track_id: int, timestamp: datetime
) -> ThreatAssessmentEvent:
    return ThreatAssessmentEvent(
        event_type="ThreatAssessmentEvent",
        source="threat_engine",
        timestamp=timestamp,
        payload=ThreatAssessmentPayload(
            camera_id=camera_id,
            track_id=track_id,
            weapon_type=WeaponType.RANGED_LETHAL,
            uniform=UniformClass.CIVILIAN,
            zone=DistanceZone.ZONE_1,
            threat_level=ThreatLevel.HIGH,
            rule_id="RANGED_LETHAL_ZONE_1",
        ),
    )


@pytest.mark.asyncio
class TestHandleEscalationCreatesIncident:
    async def test_creates_incident_and_publishes_created_then_updated(self, db_session) -> None:
        camera = await _make_camera(db_session)
        bus = InProcessEventBus()
        try:
            created: list = []
            updated: list = []
            bus.subscribe("IncidentCreatedEvent", _collecting_handler(created))
            bus.subscribe("IncidentUpdatedEvent", _collecting_handler(updated))

            service = IncidentService(db_session, bus)
            incident = await service.handle_escalation(
                camera_id=camera.id,
                track_id=42,
                threat_level=ThreatLevel.HIGH,
                reason="sustained_high_threat",
                timestamp=T0,
            )

            assert (
                incident.status is IncidentStatus.ACTIVE
            )  # after the immediate NEW->ACTIVE transition

            await asyncio.sleep(0.05)  # let the bus's background subscriber tasks drain
            assert len(created) == 1
            assert created[0].payload.status is IncidentStatus.NEW
            assert created[0].payload.incident_id == incident.id
            assert len(updated) == 1
            assert updated[0].payload.old_status is IncidentStatus.NEW
            assert updated[0].payload.new_status is IncidentStatus.ACTIVE
        finally:
            await bus.stop()

    async def test_uses_cached_threat_assessment_metadata_for_summary(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)
        await service.on_threat_assessment(_threat_assessment(camera.id, 1, T0))

        incident = await service.handle_escalation(
            camera_id=camera.id,
            track_id=1,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0,
        )

        assert incident.threat_summary == {
            "weapon": "ranged_lethal",
            "uniform": "civilian",
            "zone": "zone_1",
            "rule_id": "RANGED_LETHAL_ZONE_1",
        }

    async def test_uses_empty_summary_when_no_prior_metadata_cached(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)

        incident = await service.handle_escalation(
            camera_id=camera.id,
            track_id=2,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0,
        )

        assert incident.threat_summary == {}


@pytest.mark.asyncio
class TestIdempotency:
    """Roadmap acceptance criterion: exactly one incident per track, never duplicates."""

    async def test_repeated_escalation_calls_do_not_create_duplicate_incidents(
        self, db_session
    ) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)

        first = await service.handle_escalation(
            camera_id=camera.id,
            track_id=7,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0,
        )
        second = await service.handle_escalation(
            camera_id=camera.id,
            track_id=7,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0 + timedelta(seconds=1),
        )
        third = await service.handle_escalation(
            camera_id=camera.id,
            track_id=7,
            threat_level=ThreatLevel.HIGH,
            reason="sustained_high_threat",
            timestamp=T0 + timedelta(seconds=2),
        )

        assert first.id == second.id == third.id

        all_incidents = await IncidentRepository(db_session).list()
        matching = [i for i in all_incidents if i.camera_id == camera.id and i.track_id == 7]
        assert len(matching) == 1

    async def test_different_tracks_get_different_incidents(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)

        first = await service.handle_escalation(
            camera_id=camera.id, track_id=1, threat_level=ThreatLevel.HIGH, reason="r", timestamp=T0
        )
        second = await service.handle_escalation(
            camera_id=camera.id, track_id=2, threat_level=ThreatLevel.HIGH, reason="r", timestamp=T0
        )

        assert first.id != second.id

    async def test_create_race_falls_back_to_the_incident_that_won(self, db_session) -> None:
        """Simulates the TOCTOU race explicitly handled in handle_escalation():
        another caller's incident already exists in the DB by the time this
        caller's insert runs, even though its own initial existence check
        (deliberately faked here) reported none found."""
        camera = await _make_camera(db_session)
        conflicting = await IncidentRepository(db_session).add(
            Incident(
                camera_id=camera.id,
                track_id=8,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )
        # Commit so this survives the rollback() that handle_escalation()'s
        # race-handling path issues below -- otherwise this test's own setup
        # data would be wiped along with it, which would never happen in
        # reality (the "other caller" runs in a separate, already-committed
        # transaction by the time this one's insert conflicts).
        await db_session.commit()

        service = IncidentService(db_session)
        real_get_active_for_track = service._repo.get_active_for_track
        calls = {"n": 0}

        async def flaky_get_active_for_track(camera_id, track_id):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # simulate the race: initial check misses it
            return await real_get_active_for_track(camera_id, track_id)

        with mock.patch.object(
            service._repo, "get_active_for_track", side_effect=flaky_get_active_for_track
        ):
            result = await service.handle_escalation(
                camera_id=camera.id,
                track_id=8,
                threat_level=ThreatLevel.HIGH,
                reason="r",
                timestamp=T0,
            )

        assert result.id == conflicting.id


@pytest.mark.asyncio
class TestTrackLostSweep:
    async def test_sweep_closes_incident_after_track_lost_timeout(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)
        await service.on_threat_assessment(_threat_assessment(camera.id, 3, T0))

        incident = await service.handle_escalation(
            camera_id=camera.id, track_id=3, threat_level=ThreatLevel.HIGH, reason="r", timestamp=T0
        )

        past_timeout = T0 + timedelta(seconds=TRACK_LOST_SECONDS + 0.1)
        closed = await service.sweep_track_lost(past_timeout)

        assert len(closed) == 1
        assert closed[0].id == incident.id
        assert closed[0].status is IncidentStatus.RESOLVED
        assert closed[0].resolved_at == past_timeout

    async def test_sweep_does_not_close_recently_seen_incident(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)
        await service.on_threat_assessment(_threat_assessment(camera.id, 4, T0))
        await service.handle_escalation(
            camera_id=camera.id, track_id=4, threat_level=ThreatLevel.HIGH, reason="r", timestamp=T0
        )

        within_timeout = T0 + timedelta(seconds=TRACK_LOST_SECONDS - 1)
        closed = await service.sweep_track_lost(within_timeout)

        assert closed == []

    async def test_sweep_ignores_tracks_with_no_active_incident(self, db_session) -> None:
        camera = await _make_camera(db_session)
        service = IncidentService(db_session)
        # Track seen (e.g. a LOW-level ThreatAssessmentEvent) but never escalated.
        await service.on_threat_assessment(_threat_assessment(camera.id, 5, T0))

        past_timeout = T0 + timedelta(seconds=TRACK_LOST_SECONDS + 0.1)
        closed = await service.sweep_track_lost(past_timeout)  # must not raise

        assert closed == []

    async def test_sweep_publishes_incident_updated_event(self, db_session) -> None:
        camera = await _make_camera(db_session)
        bus = InProcessEventBus()
        try:
            updated: list = []
            bus.subscribe("IncidentUpdatedEvent", _collecting_handler(updated))

            service = IncidentService(db_session, bus)
            await service.on_threat_assessment(_threat_assessment(camera.id, 6, T0))
            await service.handle_escalation(
                camera_id=camera.id,
                track_id=6,
                threat_level=ThreatLevel.HIGH,
                reason="r",
                timestamp=T0,
            )
            updated.clear()  # drop the NEW->ACTIVE update from creation

            past_timeout = T0 + timedelta(seconds=TRACK_LOST_SECONDS + 0.1)
            await service.sweep_track_lost(past_timeout)

            await asyncio.sleep(0.05)
            assert len(updated) == 1
            assert updated[0].payload.old_status is IncidentStatus.ACTIVE
            assert updated[0].payload.new_status is IncidentStatus.RESOLVED
        finally:
            await bus.stop()
