"""Tests for services.incident_service.main -- the Incident Service
process's own internal ObservationEvent/CalibrationUpdatedEvent handling
logic (ADR-029 Phase 4/5). No DB fixtures: CalibrationService/IncidentService/
HumanReviewRepository are monkeypatched out, since this module's own job is
only to wire them together correctly, not to re-test their already-covered
business logic (services/calibration, services/incident_service.service each
have their own test suites; AlarmService moved to services/alert_service
under ADR-029 Phase 6, see tests/services/alert_service/).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.calibration.types import CalibrationNotFoundError, DistanceEstimate
from services.incident_service import main as incident_main
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.payloads import (
    BoundingBoxPayload,
    HumanReviewItemCreatedPayload,
    ObservationDetection,
    ObservationEventPayload,
    ThreatAssessmentPayload,
)
from shared.events.types import HumanReviewItemCreatedEvent, ObservationEvent, ThreatAssessmentEvent


def _make_detection(*, track_id: int | None) -> ObservationDetection:
    return ObservationDetection(
        detection_id=uuid.uuid4(),
        track_id=track_id,
        class_id=0,
        label="person",
        confidence=0.9,
        bbox=BoundingBoxPayload(left=0.1, top=0.1, width=0.2, height=0.3),
    )


def _make_observation_event(detections: list[ObservationDetection]) -> ObservationEvent:
    return ObservationEvent(
        event_type="ObservationEvent",
        source="ai_runtime",
        payload=ObservationEventPayload(
            observation_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            frame_num=1,
            frame_timestamp=datetime.now(timezone.utc),
            detections=detections,
        ),
    )


def _make_threat_assessment_event(camera_id: uuid.UUID, track_id: int) -> ThreatAssessmentEvent:
    return ThreatAssessmentEvent(
        event_type="ThreatAssessmentEvent",
        source="threat_engine",
        payload=ThreatAssessmentPayload(
            camera_id=camera_id,
            track_id=track_id,
            weapon_type=WeaponType.NONE,
            uniform=UniformClass.UNKNOWN,
            zone=DistanceZone.ZONE_1,
            threat_level=ThreatLevel.HUMAN_REVIEW,
            rule_id="unknown_uniform",
        ),
    )


def _make_human_review_event(camera_id: uuid.UUID, track_id: int) -> HumanReviewItemCreatedEvent:
    return HumanReviewItemCreatedEvent(
        event_type="HumanReviewItemCreatedEvent",
        source="threat_engine",
        payload=HumanReviewItemCreatedPayload(
            camera_id=camera_id,
            track_id=track_id,
            reason="uniform_unknown",
            review_item_id=uuid.uuid4(),
        ),
    )


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _make_session_factory():
    """Returns (session_factory, created_sessions) -- every call to
    session_factory() builds and records a brand-new fake session, so
    tests can assert no session/state leaks across events."""
    created: list[AsyncMock] = []

    def factory() -> _SessionContext:
        session = AsyncMock()
        created.append(session)
        return _SessionContext(session)

    return factory, created


@pytest.fixture
def patched_services(monkeypatch: pytest.MonkeyPatch):
    """Replaces CalibrationService/IncidentService/HumanReviewRepository
    (imported by name into services.incident_service.main) with fakes, and
    returns the fake instance constructors see, so tests can assert on
    their calls."""
    calibration_instance = MagicMock()
    calibration_instance.estimate = AsyncMock(
        return_value=DistanceEstimate(distance_meters=12.0, zone=DistanceZone.ZONE_1)
    )
    calibration_cls = MagicMock(return_value=calibration_instance)
    monkeypatch.setattr(incident_main, "CalibrationService", calibration_cls)

    incident_instance = MagicMock()
    incident_instance.handle_escalation = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    incident_instance.on_threat_assessment = AsyncMock()
    incident_cls = MagicMock(return_value=incident_instance)
    monkeypatch.setattr(incident_main, "IncidentService", incident_cls)

    review_repo_instance = MagicMock()
    review_repo_instance.get_open_for_track = AsyncMock(return_value=None)
    review_repo_instance.add = AsyncMock()
    review_repo_cls = MagicMock(return_value=review_repo_instance)
    monkeypatch.setattr(incident_main, "HumanReviewRepository", review_repo_cls)

    return calibration_cls, calibration_instance, incident_cls, incident_instance


@pytest.fixture
def review_repo(patched_services) -> MagicMock:
    """The fake HumanReviewRepository *instance* patched_services wired up
    -- a separate fixture (rather than a 5th patched_services return value)
    so every existing patched_services-only test is unaffected."""
    return incident_main.HumanReviewRepository.return_value  # type: ignore[attr-defined]


@pytest.fixture
def last_published_assessment() -> dict:
    """Fresh per-test dedup cache -- see _handle_observation's own
    docstring for why this exists (only gates the bus-publish side
    effect, not ThreatEngine's own per-frame re-emission)."""
    return {}


@pytest.mark.asyncio
async def test_untracked_detection_never_reaches_calibration_or_threat_engine(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=None)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=MagicMock(),
    )

    calibration_instance.estimate.assert_not_called()
    threat_engine.ingest.assert_not_called()
    incident_instance.handle_escalation.assert_not_called()
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_calibration_miss_skips_detection_but_continues_the_event(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, calibration_instance, _incident_cls, incident_instance = patched_services
    calibration_instance.estimate = AsyncMock(
        side_effect=CalibrationNotFoundError("no calibration")
    )
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=MagicMock(),
    )

    threat_engine.ingest.assert_not_called()
    incident_instance.handle_escalation.assert_not_called()
    sessions[0].commit.assert_awaited_once()  # continues, doesn't abort/rollback the event


@pytest.mark.asyncio
async def test_incident_eligible_never_publishes_an_alarm_eligible_event(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    signal = EscalationSignal(
        camera_id=camera_id,
        track_id=7,
        signal_type=EscalationSignalType.INCIDENT_ELIGIBLE,
        threat_level=ThreatLevel.HIGH,
        reason="sustained_high_threat",
    )
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[signal])
    bus = MagicMock()
    bus.publish = AsyncMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    incident_instance.handle_escalation.assert_awaited_once()
    kwargs = incident_instance.handle_escalation.await_args.kwargs
    assert kwargs["camera_id"] == camera_id
    assert kwargs["track_id"] == 7
    assert kwargs["threat_level"] == ThreatLevel.HIGH
    assert kwargs["reason"] == "sustained_high_threat"
    bus.publish.assert_not_called()  # INCIDENT_ELIGIBLE alone never reaches AlarmEligibleEvent
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_alarm_eligible_publishes_alarm_eligible_event_with_the_new_incident_id(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    incident_id = uuid.uuid4()
    incident_instance.handle_escalation = AsyncMock(return_value=MagicMock(id=incident_id))
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    signal = EscalationSignal(
        camera_id=camera_id,
        track_id=7,
        signal_type=EscalationSignalType.ALARM_ELIGIBLE,
        threat_level=ThreatLevel.HIGH,
        reason="sustained_high_threat",
    )
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[signal])
    bus = MagicMock()
    bus.publish = AsyncMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    bus.publish.assert_awaited_once()
    assert bus.publish.await_args is not None
    published = bus.publish.await_args.args[0]
    assert published.event_type == "AlarmEligibleEvent"
    assert published.payload.camera_id == camera_id
    assert published.payload.track_id == 7
    assert published.payload.incident_id == incident_id
    assert published.payload.threat_level == ThreatLevel.HIGH
    assert published.payload.reason == "sustained_high_threat"
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_threat_assessment_event_updates_metadata_then_publishes(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    assessment = _make_threat_assessment_event(camera_id, 7)
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[assessment])
    bus = MagicMock()
    bus.publish = AsyncMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    incident_instance.on_threat_assessment.assert_awaited_once_with(assessment)
    bus.publish.assert_awaited_once_with(assessment)
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_identical_assessment_publishes_only_once(
    patched_services, last_published_assessment
) -> None:
    """Real hardware surfaced this directly: ThreatEngine re-emits a
    ThreatAssessmentEvent every frame a track is classified (by design,
    ADR-021), but publishing every one of those to the bus flooded
    /ws/threats at full frame rate for a continuously-tracked person,
    which flooded the frontend's /threats/active refetches in turn. Only
    a *changed* assessment for a track should reach the bus."""
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    unchanged = _make_threat_assessment_event(camera_id, 7)
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[unchanged])
    bus = MagicMock()
    bus.publish = AsyncMock()
    event = _make_observation_event([_make_detection(track_id=7)])

    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    incident_instance.on_threat_assessment.assert_awaited()
    assert incident_instance.on_threat_assessment.await_count == 2  # every frame, unconditionally
    bus.publish.assert_awaited_once_with(unchanged)  # only the first, unchanged repeat skipped

    changed = ThreatAssessmentEvent(
        event_type="ThreatAssessmentEvent",
        source="threat_engine",
        payload=ThreatAssessmentPayload(
            camera_id=camera_id,
            track_id=7,
            weapon_type=WeaponType.NONE,
            uniform=UniformClass.CIVILIAN,  # changed from UNKNOWN
            zone=DistanceZone.ZONE_1,
            threat_level=ThreatLevel.OBSERVE,
            rule_id="no_weapon_observe",
        ),
    )
    threat_engine.ingest = MagicMock(return_value=[changed])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    assert bus.publish.await_count == 2
    bus.publish.assert_awaited_with(changed)


@pytest.mark.asyncio
async def test_human_review_item_created_event_persists_and_publishes(
    review_repo, last_published_assessment
) -> None:
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    review_event = _make_human_review_event(camera_id, 7)
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[review_event])
    bus = MagicMock()
    bus.publish = AsyncMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    review_repo.get_open_for_track.assert_awaited_once_with(camera_id, 7)
    review_repo.add.assert_awaited_once()
    created_item = review_repo.add.await_args.args[0]
    assert created_item.camera_id == camera_id
    assert created_item.track_id == 7
    assert created_item.reason == "uniform_unknown"
    assert created_item.status == "OPEN"
    bus.publish.assert_awaited_once_with(review_event)
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_human_review_item_skipped_when_already_open(
    review_repo, last_published_assessment
) -> None:
    """ThreatEngine's own review_signaled dedup can still miss across a
    process restart -- the pre-check backstop must skip creating a
    duplicate row, but still publish the event."""
    review_repo.get_open_for_track = AsyncMock(return_value=MagicMock())
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    review_event = _make_human_review_event(camera_id, 7)
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[review_event])
    bus = MagicMock()
    bus.publish = AsyncMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=bus,
    )

    review_repo.add.assert_not_called()
    bus.publish.assert_awaited_once_with(review_event)
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_each_call_opens_and_commits_its_own_independent_session(
    patched_services, last_published_assessment
) -> None:
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[])

    event = _make_observation_event([_make_detection(track_id=1)])
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=MagicMock(),
    )
    await incident_main._handle_observation(
        event,
        session_factory=session_factory,
        threat_engine=threat_engine,
        last_published_assessment=last_published_assessment,
        bus=MagicMock(),
    )

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    sessions[0].commit.assert_awaited_once()
    sessions[1].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mid_event_exception_rolls_back_and_propagates(
    patched_services, last_published_assessment
) -> None:
    _calibration_cls, calibration_instance, _incident_cls, _incident_instance = patched_services
    calibration_instance.estimate = AsyncMock(side_effect=RuntimeError("unexpected failure"))
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    with pytest.raises(RuntimeError, match="unexpected failure"):
        await incident_main._handle_observation(
            event,
            session_factory=session_factory,
            threat_engine=threat_engine,
            last_published_assessment=last_published_assessment,
            bus=MagicMock(),
        )

    sessions[0].rollback.assert_awaited_once()
    sessions[0].commit.assert_not_called()


@pytest.mark.asyncio
async def test_calibration_updated_clears_the_calibration_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache = MagicMock()
    monkeypatch.setattr(incident_main.calibration_service_module, "clear_cache", clear_cache)

    await incident_main._handle_calibration_updated(MagicMock())

    clear_cache.assert_called_once_with()
