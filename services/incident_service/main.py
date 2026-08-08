"""Incident Service process entrypoint (ADR-029 Phase 4).

Subscribes to ``ObservationEvent`` on the production EventBus and, for
each tracked detection, calls ``CalibrationService`` -> ``ThreatEngine``
-> ``IncidentService.handle_escalation()`` -- publishing
``IncidentCreatedEvent``/``IncidentUpdatedEvent``.

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
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.logging_config import configure_logging
from services.calibration import service as calibration_service_module
from services.calibration.service import CalibrationService
from services.calibration.types import CalibrationNotFoundError
from services.incident_service.service import IncidentService
from services.threat_engine.engine import ThreatEngine
from services.threat_engine.types import EscalationSignal
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.bus import EventBus
from shared.events.types import CalibrationUpdatedEvent, ObservationEvent
from shared.events.zmq_bus import ZmqEventBus

logger = logging.getLogger(__name__)


async def _handle_observation(
    event: ObservationEvent,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    threat_engine: ThreatEngine,
    bus: EventBus,
) -> None:
    """ObservationEvent -> Calibration -> ThreatEngine -> IncidentService.

    One short-lived session per event (SQLAlchemy's recommended unit-of-
    work pattern) -- ``session_factory``/``threat_engine``/``bus`` are the
    only long-lived collaborators, injected once at process startup.
    ``CalibrationService``/``IncidentService`` are constructed fresh
    inside this one session's scope, matching ``CalibrationService``'s
    own pre-existing documented convention ("constructed per request/
    session throughout the rest of the repository").

    No weapon/uniform classifier exists yet (PGIE/SGIE are still
    placeholder models, per configs/models.yaml) -- honestly reports
    WeaponType.NONE/UniformClass.UNKNOWN rather than a fabricated guess,
    matching the pre-ADR-029 ThreatEngineRuntimeAdapter's own defaults.
    """
    async with session_factory() as session:
        try:
            calibration_service = CalibrationService(session)
            incident_service = IncidentService(session, bus)
            for detection in event.payload.detections:
                if detection.track_id is None:
                    continue
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
                    uniform=UniformClass.UNKNOWN,
                    weapon_type=WeaponType.NONE,
                    zone=distance.zone,
                    timestamp=event.payload.frame_timestamp,
                )
                for result in results:
                    if not isinstance(result, EscalationSignal):
                        # ThreatAssessmentEvent/HumanReviewItemCreatedEvent --
                        # discarded, not published: out of scope for this
                        # phase (Incident Service publishes IncidentCreatedEvent/
                        # IncidentUpdatedEvent only).
                        continue
                    await incident_service.handle_escalation(
                        camera_id=result.camera_id,
                        track_id=result.track_id,
                        threat_level=result.threat_level,
                        reason=result.reason,
                        timestamp=datetime.now(timezone.utc),
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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

    async def _on_observation(event: ObservationEvent) -> None:
        await _handle_observation(
            event, session_factory=session_factory, threat_engine=threat_engine, bus=bus
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
