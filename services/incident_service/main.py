"""Incident Service process entrypoint (ADR-029 Phase 4).

Subscribes to ``ObservationEvent`` on the production EventBus and, for
each tracked detection, calls ``CalibrationService`` -> ``ThreatEngine``
-> ``IncidentService.handle_escalation()`` -- publishing
``IncidentCreatedEvent``/``IncidentUpdatedEvent``. When Threat Engine
reports ``EscalationSignalType.ALARM_ELIGIBLE`` (a separate, later
threshold than incident creation -- HIGH sustained >=3s vs. 1s, see
``shared/events/payloads.py``'s ``AlarmEligiblePayload``), also publishes
``AlarmEligibleEvent`` -- Alert Service (ADR-029 Phase 6, a separate
process) is the one that decides what to do with it; this module no
longer calls any alarm-triggering logic itself (moved to
``services/alert_service`` under Phase 6, per ADR-029's "no subsystem may
call another independently-deployed subsystem's internal logic directly").

The two handler functions below are Incident Service's own internal
event-handling logic, not a separate architectural component: the
EventBus knows nothing about Incident Service, and Incident Service
knows only about the EventBus -- no orchestration layer sits between
them.

Run with:
    python -m services.incident_service.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import datetime, timezone
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.logging_config import configure_logging
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.repositories.human_review import HumanReviewRepository
from services.calibration import service as calibration_service_module
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationNotFoundError
from services.incident_service.classification import (
    PERSON_LABEL,
    associate_weapons_with_persons,
)
from services.incident_service.service import IncidentService
from services.threat_engine.engine import ThreatEngine
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.events.bus import EventBus
from shared.events.payloads import (
    AlarmEligiblePayload,
    HumanReviewItemCreatedPayload,
    ThreatAssessmentPayload,
)
from shared.events.types import (
    AlarmEligibleEvent,
    CalibrationUpdatedEvent,
    HumanReviewItemCreatedEvent,
    ObservationEvent,
    ThreatAssessmentEvent,
)
from shared.events.zmq_bus import ZmqEventBus

logger = logging.getLogger(__name__)

# (weapon_type, uniform, zone, threat_level, rule_id) of the last
# ThreatAssessmentEvent actually published to the bus for a track --
# see _should_publish_assessment()'s docstring for why this exists.
_AssessmentKey = tuple[uuid.UUID, int]
_AssessmentSignature = tuple[str, str, str, str, str]


async def _handle_observation(
    event: ObservationEvent,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    threat_engine: ThreatEngine,
    bus: EventBus,
    last_published_assessment: dict[_AssessmentKey, _AssessmentSignature],
) -> None:
    """ObservationEvent -> Calibration -> ThreatEngine -> IncidentService.

    One short-lived session per event (SQLAlchemy's recommended unit-of-
    work pattern) -- ``session_factory``/``threat_engine``/``bus`` are the
    only long-lived collaborators, injected once at process startup.
    ``CalibrationService``/``IncidentService`` are constructed fresh inside
    this one session's scope, matching ``CalibrationService``'s own
    pre-existing documented convention ("constructed per request/session
    throughout the rest of the repository").

    Threat Engine tracks per-*person* subjects, so only ``"person"``
    detections are fed to it -- ``associate_weapons_with_persons()``
    (services/incident_service/classification.py) resolves each
    person's uniform/nearest-weapon once per event, since the detector
    reports a person and a weapon as separate detections, never one
    combined "person carrying a weapon" detection.

    ``ThreatEngine.ingest()`` returns a ``ThreatAssessmentEvent`` first,
    then zero or more ``EscalationSignal``/``HumanReviewItemCreatedEvent``
    (see ``engine.py``) -- dispatched here in that same order, since
    ``EscalationSignal`` handling below depends on
    ``on_threat_assessment()`` having already cached this event's
    weapon/uniform/zone metadata for ``handle_escalation()``'s
    ``threat_summary``.

    ``ThreatEngine`` deliberately re-emits a ``ThreatAssessmentEvent``
    every single frame a track is classified (THREAT_ENGINE_SPEC.md's
    continuous-audit design, ADR-021) -- ``on_threat_assessment()`` is
    cheap and idempotent for a repeated identical assessment, so it still
    runs every time. Publishing every one of those onto the bus is a
    different matter: a real hardware run with one continuously-tracked
    person surfaced this directly -- at ~25fps that is ~25 WebSocket
    messages/second on ``/ws/threats``, and the frontend's
    ``useActiveThreats()`` invalidates+refetches ``/threats/active`` on
    every single message, which showed up as an actual browser network
    flood (hundreds of identical ``GET /threats/active`` requests/second)
    starving the page's other WebSocket connections. ``last_published_assessment``
    is this dispatch loop's own de-dup: publish only when the assessment
    actually changed for this track since the last one *published* (not
    the last one computed) -- ``ThreatEngine``'s own state is untouched,
    this only gates the bus-publish side effect.
    """
    async with session_factory() as session:
        try:
            calibration_service = CalibrationService(session)
            incident_service = IncidentService(session, bus)
            human_review_repo = HumanReviewRepository(session)
            person_classifications = associate_weapons_with_persons(event.payload.detections)
            for detection in event.payload.detections:
                if detection.track_id is None or detection.label != PERSON_LABEL:
                    continue
                uniform, weapon_type = person_classifications[detection.track_id]
                # Ground-plane contact point: bottom-center of the bounding
                # box (CAMERA_CALIBRATION_SPEC.md's ground-plane projection
                # assumes the object touches the ground there).
                image_x = detection.bbox.left + detection.bbox.width / 2
                image_y = detection.bbox.top + detection.bbox.height
                try:
                    distance = await calibration_service.estimate(
                        camera_id=event.payload.camera_id, image_x=image_x, image_y=image_y
                    )
                except CalibrationNotFoundError:
                    continue

                results = threat_engine.ingest(
                    camera_id=event.payload.camera_id,
                    track_id=detection.track_id,
                    uniform=uniform,
                    weapon_type=weapon_type,
                    zone=distance.zone,
                    timestamp=event.payload.frame_timestamp,
                )
                for result in results:
                    # ThreatAssessmentEvent/HumanReviewItemCreatedEvent are
                    # EventEnvelope[...] generic aliases (shared/events/types.py)
                    # -- isinstance() can't check a parameterized generic, so
                    # discriminate on the concrete payload class instead.
                    # EscalationSignal (the one variant with no .payload) is
                    # checked first so the other branches' .payload access
                    # never runs against it.
                    if isinstance(result, EscalationSignal):
                        incident = await incident_service.handle_escalation(
                            camera_id=result.camera_id,
                            track_id=result.track_id,
                            threat_level=result.threat_level,
                            reason=result.reason,
                            timestamp=datetime.now(timezone.utc),
                        )
                        if result.signal_type is EscalationSignalType.ALARM_ELIGIBLE:
                            # Republish onto the bus rather than calling Alert
                            # Service in-process (ADR-029 governing principle
                            # 2: no cross-subsystem in-process calls) -- see
                            # AlarmEligiblePayload's docstring for why this
                            # event exists at all.
                            await bus.publish(
                                AlarmEligibleEvent(
                                    event_type="AlarmEligibleEvent",
                                    source="incident_service",
                                    payload=AlarmEligiblePayload(
                                        incident_id=incident.id,
                                        camera_id=result.camera_id,
                                        track_id=result.track_id,
                                        threat_level=result.threat_level,
                                        reason=result.reason,
                                    ),
                                )
                            )
                    elif isinstance(result.payload, ThreatAssessmentPayload):
                        await incident_service.on_threat_assessment(
                            cast(ThreatAssessmentEvent, result)
                        )
                        assessment_key = (result.payload.camera_id, result.payload.track_id)
                        signature = (
                            result.payload.weapon_type.value,
                            result.payload.uniform.value,
                            result.payload.zone.value,
                            result.payload.threat_level.value,
                            result.payload.rule_id,
                        )
                        if last_published_assessment.get(assessment_key) != signature:
                            last_published_assessment[assessment_key] = signature
                            await bus.publish(result)
                    elif isinstance(result.payload, HumanReviewItemCreatedPayload):
                        await _create_review_item_if_absent(
                            session, human_review_repo, cast(HumanReviewItemCreatedEvent, result)
                        )
                        await bus.publish(result)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _create_review_item_if_absent(
    session: AsyncSession, repo: HumanReviewRepository, event: HumanReviewItemCreatedEvent
) -> None:
    """Idempotent create: ``ThreatEngine``'s own ``review_signaled`` flag
    (in-memory, per-process) already prevents re-firing for a continuous
    HUMAN_REVIEW streak, but resets on restart -- this pre-check plus the
    ``ux_human_review_items_open_camera_track`` unique index (caught here,
    matching ``IncidentService.handle_escalation()``'s own lost-create-race
    handling) is the DB-level backstop, same reasoning as incidents'
    dedup."""
    payload = event.payload
    existing = await repo.get_open_for_track(payload.camera_id, payload.track_id)
    if existing is not None:
        return
    try:
        await repo.add(
            HumanReviewItem(
                camera_id=payload.camera_id,
                track_id=payload.track_id,
                reason=payload.reason,
                status="OPEN",
            )
        )
    except IntegrityError:
        await session.rollback()


async def _handle_calibration_updated(_event: CalibrationUpdatedEvent) -> None:
    """Invalidate CalibrationService's per-process cache. Required, not
    deferred: recalibration happens in apps.api, estimation happens here,
    in a different process -- without this, a recalibration would
    silently never take effect in Incident Service."""
    calibration_service_module.clear_cache()


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    logger.info(
        "radar-eye-incident-service starting", extra={"environment": api_settings.environment}
    )

    engine = create_engine(api_settings)
    session_factory = create_session_factory(engine)
    bus = ZmqEventBus(source="incident_service")
    threat_engine = ThreatEngine()
    last_published_assessment: dict[_AssessmentKey, _AssessmentSignature] = {}

    async def _on_observation(event: ObservationEvent) -> None:
        await _handle_observation(
            event,
            session_factory=session_factory,
            threat_engine=threat_engine,
            bus=bus,
            last_published_assessment=last_published_assessment,
        )

    bus.subscribe("ObservationEvent", _on_observation)
    bus.subscribe("CalibrationUpdatedEvent", _handle_calibration_updated)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("radar-eye-incident-service running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-incident-service shutting down")
        await bus.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
