"""Incident Center REST router -- RM-12 Phase 3 (reads) + Phase 4 (write).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Incident Center / Live
  Monitoring / Tactical Map sections.
  - GET /incidents
  - GET /incidents/{incident_id}
  - GET /incidents/{incident_id}/events
  - GET /incidents/{incident_id}/evidence
  - GET /incidents/open
  - PATCH /incidents/{incident_id}

``PATCH /incidents/{incident_id}`` (Phase 4, operator-gated, audit-logged)
calls only ``IncidentService.request_transition()``
(services/incident_service/service.py -- see the
``[Cross-Subsystem] IncidentService`` commit) -- never writes to
``IncidentRepository`` directly, per docs/RM-12_ARCHITECTURE.md §3.3.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.incident import Incident, IncidentEvent
from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.models.user import ROLE_OPERATOR
from apps.api.app.repositories.incident import IncidentEventRepository, IncidentRepository
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import (
    get_audit_logger,
    get_current_user,
    get_db_session,
    require_role,
)
from services.incident_service.service import IncidentService, IncidentTransitionError
from shared.schemas.api import ApiResponse
from shared.schemas.evidence import EvidenceItemSchema
from shared.schemas.incident import (
    IncidentEventSchema,
    IncidentSchema,
    IncidentSummarySchema,
    IncidentTransitionRequestSchema,
)

router = APIRouter(tags=["Incident Center"], dependencies=[Depends(get_current_user)])


def _to_incident_schema(incident: Incident) -> IncidentSchema:
    return IncidentSchema(
        incident_id=incident.id,
        camera_id=incident.camera_id,
        track_id=incident.track_id,
        incident_type=incident.incident_type,
        threat_level=incident.threat_level,
        status=incident.status,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def _to_summary_schema(incident: Incident) -> IncidentSummarySchema:
    return IncidentSummarySchema(
        incident_id=incident.id,
        camera_id=incident.camera_id,
        threat_level=incident.threat_level,
        status=incident.status,
    )


def _to_event_schema(event: IncidentEvent) -> IncidentEventSchema:
    return IncidentEventSchema(
        event_id=event.id,
        incident_id=event.incident_id,
        event_type=event.event_type,
        event_payload=event.event_payload,
        created_at=event.created_at,
    )


def _snapshot_to_evidence(snapshot: Snapshot) -> EvidenceItemSchema:
    return EvidenceItemSchema(
        evidence_id=snapshot.id,
        evidence_type="snapshot",
        incident_id=snapshot.incident_id,
        camera_id=snapshot.camera_id,
        captured_at=snapshot.captured_at,
        download_url=f"/snapshots/{snapshot.id}/download",
    )


def _recording_to_evidence(recording: Recording) -> EvidenceItemSchema:
    return EvidenceItemSchema(
        evidence_id=recording.id,
        evidence_type="recording",
        incident_id=recording.incident_id,
        camera_id=recording.camera_id,
        captured_at=recording.start_time,
        download_url=f"/recordings/{recording.id}/download",
    )


@router.get("/incidents", response_model=ApiResponse[list[IncidentSummarySchema]])
async def list_incidents(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[IncidentSummarySchema]]:
    incidents = await IncidentRepository(session).list()
    return ApiResponse(success=True, data=[_to_summary_schema(i) for i in incidents])


@router.get("/incidents/open", response_model=ApiResponse[list[IncidentSummarySchema]])
async def list_open_incidents(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[IncidentSummarySchema]]:
    incidents = await IncidentRepository(session).list_open()
    return ApiResponse(success=True, data=[_to_summary_schema(i) for i in incidents])


@router.get("/incidents/{incident_id}", response_model=ApiResponse[IncidentSchema])
async def get_incident(
    incident_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[IncidentSchema]:
    incident = await IncidentRepository(session).get(incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return ApiResponse(success=True, data=_to_incident_schema(incident))


@router.get(
    "/incidents/{incident_id}/events",
    response_model=ApiResponse[list[IncidentEventSchema]],
)
async def list_incident_events(
    incident_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[IncidentEventSchema]]:
    if await IncidentRepository(session).get(incident_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    events = await IncidentEventRepository(session).list_by_incident(incident_id)
    return ApiResponse(success=True, data=[_to_event_schema(e) for e in events])


@router.get(
    "/incidents/{incident_id}/evidence",
    response_model=ApiResponse[list[EvidenceItemSchema]],
)
async def list_incident_evidence(
    incident_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[EvidenceItemSchema]]:
    if await IncidentRepository(session).get(incident_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    snapshots = await SnapshotRepository(session).list_by_incident(incident_id)
    recordings = await RecordingRepository(session).list_by_incident(incident_id)
    evidence = [_snapshot_to_evidence(s) for s in snapshots] + [
        _recording_to_evidence(r) for r in recordings
    ]
    evidence.sort(key=lambda item: item.captured_at)
    return ApiResponse(success=True, data=evidence)


@router.patch("/incidents/{incident_id}", response_model=ApiResponse[IncidentSchema])
async def update_incident(
    incident_id: uuid.UUID,
    body: IncidentTransitionRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_OPERATOR))],
) -> ApiResponse[IncidentSchema]:
    incident = await IncidentRepository(session).get(incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    old_status = incident.status
    try:
        await IncidentService(session).request_transition(
            incident, body.status, now=datetime.now(timezone.utc)
        )
    except IncidentTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # updated_at is server-computed (onupdate=func.now()) -- unlike a
    # server_default populated via RETURNING on INSERT, an UPDATE's
    # onupdate value is not auto-refreshed into the Python object; an
    # explicit refresh() is required before it can be read back.
    await session.refresh(incident)

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="TRANSITION_INCIDENT",
        resource_type="incident",
        resource_id=str(incident.id),
        details={"old_status": old_status.value, "new_status": incident.status.value},
    )
    # Built before commit() -- commit() expires ORM attributes by default,
    # and a post-commit attribute access would lazy-load outside the
    # request's async context (MissingGreenlet).
    response_data = _to_incident_schema(incident)
    await session.commit()
    return ApiResponse(success=True, data=response_data)
