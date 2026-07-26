from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.repositories.base import Repository


class SnapshotRepository(Repository[Snapshot]):
    model = Snapshot

    async def get_by_incident_id(self, incident_id: uuid.UUID) -> Snapshot | None:
        """Finds a snapshot record by incident_id."""
        stmt = select(Snapshot).where(Snapshot.incident_id == incident_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_incident(self, incident_id: uuid.UUID) -> list[Snapshot]:
        """Lists snapshot records for a given incident_id."""
        stmt = select(Snapshot).where(Snapshot.incident_id == incident_id)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())


class RecordingRepository(Repository[Recording]):
    model = Recording

    async def get_by_incident_id(self, incident_id: uuid.UUID) -> Recording | None:
        """Finds an event clip recording record by incident_id."""
        stmt = select(Recording).where(Recording.incident_id == incident_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_incident(self, incident_id: uuid.UUID) -> list[Recording]:
        """Lists recording records for a given incident_id."""
        stmt = select(Recording).where(Recording.incident_id == incident_id)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_expired(self, cutoff_time: datetime) -> list[Recording]:
        """Lists recordings ending before the specified cutoff timestamp."""
        stmt = select(Recording).where(Recording.end_time < cutoff_time)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
