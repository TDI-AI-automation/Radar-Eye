from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

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

    async def list_by_camera(self, camera_id: uuid.UUID) -> Sequence[Incident]:
        """Every incident for a camera, any status -- backs camera deletion's
        evidence cascade (``CameraRegistryService.delete()``)."""
        result = await self._session.execute(
            select(Incident).where(Incident.camera_id == camera_id)
        )
        return result.scalars().all()

    async def list_open(self) -> Sequence[Incident]:
        """Incidents in any of ``ACTIVE_INCIDENT_STATUSES`` -- backs
        ``GET /incidents/open`` (Live Monitoring / Tactical Map)."""
        result = await self._session.execute(
            select(Incident)
            .where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
            .order_by(Incident.created_at.desc())
        )
        return result.scalars().all()

    async def count_by_threat_level(self) -> dict[str, int]:
        """Backs ``GET /analytics/threats`` (docs/RM-12_ARCHITECTURE.md §4 --
        straightforward repository-query aggregation, no analytics engine)."""
        result = await self._session.execute(
            select(Incident.threat_level, func.count()).group_by(Incident.threat_level)
        )
        return {level.value: count for level, count in result.all()}

    async def count_by_status(self) -> dict[str, int]:
        """Backs ``GET /analytics/incidents``."""
        result = await self._session.execute(
            select(Incident.status, func.count()).group_by(Incident.status)
        )
        return {status.value: count for status, count in result.all()}

    async def count_by_camera(self) -> dict[uuid.UUID, int]:
        """Backs ``GET /analytics/cameras``."""
        result = await self._session.execute(
            select(Incident.camera_id, func.count()).group_by(Incident.camera_id)
        )
        return {camera_id: count for camera_id, count in result.all()}


class IncidentEventRepository(Repository[IncidentEvent]):
    model = IncidentEvent

    async def list_by_incident(self, incident_id: uuid.UUID) -> Sequence[IncidentEvent]:
        """Backs ``GET /incidents/{incident_id}/events``, oldest first."""
        result = await self._session.execute(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at)
        )
        return result.scalars().all()
