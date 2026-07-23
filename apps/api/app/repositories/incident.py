from __future__ import annotations

import uuid

from sqlalchemy import select

from apps.api.app.models.incident import ACTIVE_INCIDENT_STATUSES, Incident, IncidentEvent
from apps.api.app.repositories.base import Repository


class IncidentRepository(Repository[Incident]):
    model = Incident

    async def get_active_for_track(self, camera_id: uuid.UUID, track_id: int) -> Incident | None:
        """The current active incident for (camera_id, track_id), if any."""
        result = await self._session.execute(
            select(Incident).where(
                Incident.camera_id == camera_id,
                Incident.track_id == track_id,
                Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
            )
        )
        return result.scalar_one_or_none()


class IncidentEventRepository(Repository[IncidentEvent]):
    model = IncidentEvent
