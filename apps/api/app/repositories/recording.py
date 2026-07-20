from __future__ import annotations

from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.repositories.base import Repository


class SnapshotRepository(Repository[Snapshot]):
    model = Snapshot


class RecordingRepository(Repository[Recording]):
    model = Recording
