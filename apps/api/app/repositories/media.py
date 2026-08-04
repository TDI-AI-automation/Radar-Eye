"""Repositories for the Media Distribution Interface's cross-process
tables (ADR-028). Both ``set_*`` methods are upserts, matching each
table's sole-writer-per-(camera, subsystem) contract: a publishing/
reporting subsystem calls this on every publish or health tick, never
needing to know whether its own row already exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from apps.api.app.models.media import CameraMediaEndpoint, CameraSubsystemHealth
from apps.api.app.repositories.base import Repository


class CameraMediaEndpointRepository(Repository[CameraMediaEndpoint]):
    model = CameraMediaEndpoint

    async def get_by_camera_and_subsystem(
        self, camera_id: uuid.UUID, subsystem: str
    ) -> CameraMediaEndpoint | None:
        result = await self._session.execute(
            select(CameraMediaEndpoint).where(
                CameraMediaEndpoint.camera_id == camera_id,
                CameraMediaEndpoint.subsystem == subsystem,
            )
        )
        return result.scalar_one_or_none()

    async def set_endpoint(
        self, camera_id: uuid.UUID, subsystem: str, *, transport: str, address: str
    ) -> CameraMediaEndpoint:
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            existing.transport = transport
            existing.address = address
            await self._session.flush()
            return existing
        return await self.add(
            CameraMediaEndpoint(
                camera_id=camera_id, subsystem=subsystem, transport=transport, address=address
            )
        )

    async def delete_endpoint(self, camera_id: uuid.UUID, subsystem: str) -> None:
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            await self.delete(existing)


class CameraSubsystemHealthRepository(Repository[CameraSubsystemHealth]):
    model = CameraSubsystemHealth

    async def get_by_camera_and_subsystem(
        self, camera_id: uuid.UUID, subsystem: str
    ) -> CameraSubsystemHealth | None:
        result = await self._session.execute(
            select(CameraSubsystemHealth).where(
                CameraSubsystemHealth.camera_id == camera_id,
                CameraSubsystemHealth.subsystem == subsystem,
            )
        )
        return result.scalar_one_or_none()

    async def set_health(
        self, camera_id: uuid.UUID, subsystem: str, *, status: str, detail: str | None = None
    ) -> CameraSubsystemHealth:
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            existing.status = status
            existing.detail = detail
            await self._session.flush()
            return existing
        return await self.add(
            CameraSubsystemHealth(
                camera_id=camera_id, subsystem=subsystem, status=status, detail=detail
            )
        )
