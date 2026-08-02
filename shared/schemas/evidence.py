"""Evidence API schemas -- RM-12 Phase 3.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Evidence Viewer section
  (GET /evidence, GET /recordings, GET /snapshots, and their /download
  routes). Backs CLAUDE.md's Evidence Preservation rule: every HIGH-threat
  incident retains a snapshot, an event clip, and an incident timeline.

There is no dedicated ``evidence`` table (docs/DATABASE_SCHEMA.md) -- a
"piece of evidence" is either a ``snapshots`` row or a ``recordings`` row.
``EvidenceItemSchema`` is the unified, read-only view over both, used by
``GET /evidence`` and ``GET /incidents/{id}/evidence``; ``RecordingSchema``/
``SnapshotSchema`` are the type-specific shapes for ``GET /recordings*`` and
``GET /snapshots*``. None of the three exposes the on-disk ``file_path`` --
only a ``download_url`` pointing at this router's own ``/download`` route,
matching CLAUDE.md's "avoid mock data" spirit applied to not leaking server
filesystem layout to the frontend.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EvidenceType = Literal["snapshot", "recording"]


class SnapshotSchema(BaseModel):
    """Returned by ``GET /snapshots/{snapshot_id}``."""

    snapshot_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    captured_at: datetime
    download_url: str


class RecordingSchema(BaseModel):
    """Returned by ``GET /recordings/{recording_id}``."""

    recording_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    created_at: datetime
    download_url: str


class EvidenceItemSchema(BaseModel):
    """Unified snapshot-or-recording view for ``GET /evidence`` and
    ``GET /incidents/{incident_id}/evidence``."""

    evidence_id: uuid.UUID
    evidence_type: EvidenceType
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    captured_at: datetime
    """``snapshots.captured_at`` for a snapshot; ``recordings.start_time``
    for a recording -- the moment the evidence begins, for chronological
    sorting across both types."""
    download_url: str
