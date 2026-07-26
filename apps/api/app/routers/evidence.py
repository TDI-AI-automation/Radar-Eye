"""Evidence Viewer REST router -- RM-12 Phase 3.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Evidence Viewer section.
  - GET /evidence
  - GET /evidence/{evidence_id}
  - GET /recordings
  - GET /recordings/{recording_id}
  - GET /recordings/{recording_id}/download
  - GET /snapshots/{snapshot_id}
  - GET /snapshots/{snapshot_id}/download

(No ``GET /snapshots`` list route -- the contract only lists a single-item
GET and a download route for snapshots, unlike recordings.)

**Download route design** (open point flagged in
docs/RM-12_IMPLEMENTATION_PLAN.md Phase 3, resolved here): a direct,
authenticated file stream (``FileResponse``) rather than a signed URL.
Radar Eye is a single-node, air-gapped deployment with local filesystem
evidence storage (CLAUDE.md's Offline First / Recording Rules) -- there is
no multi-tenant or distributed-storage boundary a signed URL would need to
cross, and no existing signed-URL infrastructure in this repo. The route
itself is already behind the same JWT bearer auth as every other Phase 3
route; that is the access control.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from apps.api.app.security.dependencies import get_current_user, get_db_session
from shared.schemas.api import ApiResponse
from shared.schemas.evidence import EvidenceItemSchema, RecordingSchema, SnapshotSchema

router = APIRouter(tags=["Evidence Viewer"], dependencies=[Depends(get_current_user)])


def _to_recording_schema(recording: Recording) -> RecordingSchema:
    return RecordingSchema(
        recording_id=recording.id,
        incident_id=recording.incident_id,
        camera_id=recording.camera_id,
        start_time=recording.start_time,
        end_time=recording.end_time,
        created_at=recording.created_at,
        download_url=f"/recordings/{recording.id}/download",
    )


def _to_snapshot_schema(snapshot: Snapshot) -> SnapshotSchema:
    return SnapshotSchema(
        snapshot_id=snapshot.id,
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


def _snapshot_to_evidence(snapshot: Snapshot) -> EvidenceItemSchema:
    return EvidenceItemSchema(
        evidence_id=snapshot.id,
        evidence_type="snapshot",
        incident_id=snapshot.incident_id,
        camera_id=snapshot.camera_id,
        captured_at=snapshot.captured_at,
        download_url=f"/snapshots/{snapshot.id}/download",
    )


def _file_response(file_path: str) -> FileResponse:
    path = Path(file_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence file not present on disk")
    return FileResponse(path)


@router.get("/evidence", response_model=ApiResponse[list[EvidenceItemSchema]])
async def list_evidence(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[EvidenceItemSchema]]:
    recordings = await RecordingRepository(session).list()
    snapshots = await SnapshotRepository(session).list()
    evidence = [_recording_to_evidence(r) for r in recordings] + [
        _snapshot_to_evidence(s) for s in snapshots
    ]
    evidence.sort(key=lambda item: item.captured_at, reverse=True)
    return ApiResponse(success=True, data=evidence)


@router.get("/evidence/{evidence_id}", response_model=ApiResponse[EvidenceItemSchema])
async def get_evidence(
    evidence_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[EvidenceItemSchema]:
    """``evidence_id`` has no single backing table -- it is either a
    ``recordings.id`` or a ``snapshots.id`` (see module docstring)."""
    recording = await RecordingRepository(session).get(evidence_id)
    if recording is not None:
        return ApiResponse(success=True, data=_recording_to_evidence(recording))

    snapshot = await SnapshotRepository(session).get(evidence_id)
    if snapshot is not None:
        return ApiResponse(success=True, data=_snapshot_to_evidence(snapshot))

    raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")


@router.get("/recordings", response_model=ApiResponse[list[RecordingSchema]])
async def list_recordings(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[RecordingSchema]]:
    recordings = await RecordingRepository(session).list()
    return ApiResponse(success=True, data=[_to_recording_schema(r) for r in recordings])


@router.get("/recordings/{recording_id}", response_model=ApiResponse[RecordingSchema])
async def get_recording(
    recording_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[RecordingSchema]:
    recording = await RecordingRepository(session).get(recording_id)
    if recording is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    return ApiResponse(success=True, data=_to_recording_schema(recording))


@router.get("/recordings/{recording_id}/download")
async def download_recording(
    recording_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FileResponse:
    recording = await RecordingRepository(session).get(recording_id)
    if recording is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    return _file_response(recording.file_path)


@router.get("/snapshots/{snapshot_id}", response_model=ApiResponse[SnapshotSchema])
async def get_snapshot(
    snapshot_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[SnapshotSchema]:
    snapshot = await SnapshotRepository(session).get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot not found")
    return ApiResponse(success=True, data=_to_snapshot_schema(snapshot))


@router.get("/snapshots/{snapshot_id}/download")
async def download_snapshot(
    snapshot_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FileResponse:
    snapshot = await SnapshotRepository(session).get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot not found")
    return _file_response(snapshot.file_path)
