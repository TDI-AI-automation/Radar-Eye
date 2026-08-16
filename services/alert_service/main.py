"""Alert Service process entrypoint (ADR-029 Phase 6).

Subscribes to ``IncidentCreatedEvent``, ``AlarmEligibleEvent``, and
``IncidentUpdatedEvent`` on the production EventBus. Owns alert generation,
severity, deduplication, and operator notification (``AlertService``,
service.py) plus the HIGH/FIRE alarm-eligibility rule relocated from
ADR-026's undifferentiated "Alarm Service" (``AlarmService``, alarm.py).

Two separate, siblings-not-nested outputs per incident, matching
EVENT_CONTRACTS.md exactly:
  - Every incident raises an ``AlertRaisedEvent`` (operator notification;
    any severity).
  - Only a track that crossed Threat Engine's ALARM_ELIGIBLE threshold
    (HIGH sustained >=3s, or FIRE immediate -- see
    ``shared/events/payloads.py``'s ``AlarmEligiblePayload`` docstring for
    why this needs its own event) also produces an ``AlarmRequestedEvent``
    for the future Hardware Action Service (ADR-029 Phase 7).

Run with:
    python -m services.alert_service.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.logging_config import configure_logging
from services.alert_service.alarm import AlarmService
from services.alert_service.service import AlertService
from shared.constants.incident_types import IncidentStatus
from shared.events.types import AlarmEligibleEvent, IncidentCreatedEvent, IncidentUpdatedEvent
from shared.events.zmq_bus import ZmqEventBus

logger = logging.getLogger(__name__)

_RESOLVING_STATUSES = frozenset({IncidentStatus.RESOLVED, IncidentStatus.ARCHIVED})


async def _handle_incident_created(
    event: IncidentCreatedEvent, *, alert_service: AlertService
) -> None:
    """Every incident raises an alert -- unlike alarm-eligibility, this is
    not filtered by threat_level (an operator is notified of any incident,
    per ADR-029 Phase 6's scope; only HIGH/FIRE additionally alarms, and
    that path is driven by ``AlarmEligibleEvent`` below, not this event)."""
    await alert_service.raise_alert(
        incident_id=event.payload.incident_id,
        camera_id=event.payload.camera_id,
        severity=event.payload.threat_level,
        timestamp=event.timestamp,
    )


async def _handle_alarm_eligible(event: AlarmEligibleEvent, *, alarm_service: AlarmService) -> None:
    """Threat Engine (via Incident Service, the process that observes its
    EscalationSignal return values) already decided this track crossed the
    HIGH-sustained->=3s/FIRE threshold -- trigger() itself re-validates
    ADR-026's HIGH/FIRE filter but contains no timing logic of its own."""
    await alarm_service.trigger(
        camera_id=event.payload.camera_id,
        track_id=event.payload.track_id,
        incident_id=event.payload.incident_id,
        threat_level=event.payload.threat_level,
        reason=event.payload.reason,
        timestamp=event.timestamp,
    )


async def _handle_incident_updated(
    event: IncidentUpdatedEvent, *, alert_service: AlertService, alarm_service: AlarmService
) -> None:
    """Resolve this incident's alert/alarm once it reaches a terminal
    status. No-op (both resolve()/clear() are idempotent-safe) for an
    incident that never had an active alert/alarm (e.g. a MEDIUM incident
    that never crossed ALARM_ELIGIBLE)."""
    if event.payload.new_status not in _RESOLVING_STATUSES:
        return
    await alert_service.resolve(event.payload.incident_id)
    await alarm_service.clear(event.payload.incident_id)


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    logger.info("radar-eye-alert-service starting", extra={"environment": api_settings.environment})

    bus = ZmqEventBus(source="alert_service")
    alert_service = AlertService(bus=bus)
    alarm_service = AlarmService(bus=bus)

    async def _on_incident_created(event: IncidentCreatedEvent) -> None:
        await _handle_incident_created(event, alert_service=alert_service)

    async def _on_alarm_eligible(event: AlarmEligibleEvent) -> None:
        await _handle_alarm_eligible(event, alarm_service=alarm_service)

    async def _on_incident_updated(event: IncidentUpdatedEvent) -> None:
        await _handle_incident_updated(
            event, alert_service=alert_service, alarm_service=alarm_service
        )

    bus.subscribe("IncidentCreatedEvent", _on_incident_created)
    bus.subscribe("AlarmEligibleEvent", _on_alarm_eligible)
    bus.subscribe("IncidentUpdatedEvent", _on_incident_updated)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("radar-eye-alert-service running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-alert-service shutting down")
        await alarm_service.stop()
        await bus.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
