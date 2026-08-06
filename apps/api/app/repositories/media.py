"""Repositories for the Media Distribution Interface's cross-process
tables (ADR-028). Both ``set_*`` methods are upserts, matching each
table's sole-writer-per-(camera, subsystem) contract: a publishing/
reporting subsystem calls this on every publish or health tick, never
needing to know whether its own row already exists.

Both ``set_*`` methods also tolerate a real, observed race: the camera
these rows reference can be deleted (by an operator, via ``apps.api``)
between a reporting subsystem's roster read and its next write for that
same camera_id -- Camera Ingestion/Live Streaming's own removal path
writes a final "endpoint removed"/"DISCONNECTED" row for exactly this
transition. When the camera is already gone, that write's only possible
outcome is a foreign key violation, which is retried nowhere and helps
no one -- there is no camera left to report health for, so the write is
silently skipped rather than crash-looping the reporting subsystem's own
synchronize loop forever (confirmed on real hardware: this exact
sequence -- delete a camera, then Live Streaming's next sync tick tries
to write its removal health row -- reproduced the crash loop, not a
hypothetical).
"""

from __future__ import annotations

import uuid

from asyncpg.exceptions import ForeignKeyViolationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.api.app.models.media import CameraMediaEndpoint, CameraSubsystemHealth
from apps.api.app.repositories.base import Repository


def _is_camera_foreign_key_violation(exc: IntegrityError) -> bool:
    """True only for the specific "camera_id doesn't exist" race this
    module tolerates -- never for a duplicate-(camera_id, subsystem)
    violation, which would indicate a real sole-writer-contract bug and
    must keep propagating.

    ``exc.orig`` is SQLAlchemy's asyncpg DBAPI adapter's own wrapper
    exception, not the driver-level one -- confirmed empirically (not
    assumed) against this exact stack: the real ``asyncpg.exceptions.*``
    exception is one level deeper, at ``exc.orig.__cause__``."""
    if exc.orig is None:
        return False
    return isinstance(exc.orig.__cause__, ForeignKeyViolationError)


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
    ) -> CameraMediaEndpoint | None:
        """Returns ``None`` (rather than raising) if ``camera_id`` no
        longer exists -- see this module's docstring for the race this
        tolerates. Every other failure still propagates."""
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            existing.transport = transport
            existing.address = address
            await self._session.flush()
            return existing
        try:
            return await self.add(
                CameraMediaEndpoint(
                    camera_id=camera_id, subsystem=subsystem, transport=transport, address=address
                )
            )
        except IntegrityError as exc:
            if not _is_camera_foreign_key_violation(exc):
                raise
            await self._session.rollback()
            return None

    async def delete_endpoint(self, camera_id: uuid.UUID, subsystem: str) -> None:
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            await self.delete(existing)

    async def list_by_subsystem(self, subsystem: str) -> list[CameraMediaEndpoint]:
        """Every camera currently published by ``subsystem`` -- how a
        downstream consumer (e.g. Live Streaming) discovers what to
        subscribe to. Deliberately camera-scoped, not credential-scoped:
        a consumer using this never touches ``cameras``/
        ``camera_stream_profiles`` at all, only ``MediaEndpoint``-shaped
        rows (ADR-028's "it only knows MediaEndpoint" boundary)."""
        result = await self._session.execute(
            select(CameraMediaEndpoint).where(CameraMediaEndpoint.subsystem == subsystem)
        )
        return list(result.scalars().all())

    async def list_by_camera(self, camera_id: uuid.UUID) -> list[CameraMediaEndpoint]:
        """Every published-endpoint row for one camera, across every
        subsystem that has ever published it -- used by
        ``CameraRegistryService.delete()`` to clean this ephemeral runtime
        bookkeeping up before deleting the camera itself. Not evidence
        (CLAUDE.md's Evidence Preservation principle doesn't apply): this
        is "which endpoint is currently published," re-created automatically
        the moment a camera is re-registered, never an audit trail."""
        result = await self._session.execute(
            select(CameraMediaEndpoint).where(CameraMediaEndpoint.camera_id == camera_id)
        )
        return list(result.scalars().all())


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
    ) -> CameraSubsystemHealth | None:
        """Returns ``None`` (rather than raising) if ``camera_id`` no
        longer exists -- see this module's docstring for the race this
        tolerates (a subsystem's own "removed"/"DISCONNECTED" health
        write for a camera that was deleted out from under it). Every
        other failure still propagates."""
        existing = await self.get_by_camera_and_subsystem(camera_id, subsystem)
        if existing is not None:
            existing.status = status
            existing.detail = detail
            await self._session.flush()
            return existing
        try:
            return await self.add(
                CameraSubsystemHealth(
                    camera_id=camera_id, subsystem=subsystem, status=status, detail=detail
                )
            )
        except IntegrityError as exc:
            if not _is_camera_foreign_key_violation(exc):
                raise
            await self._session.rollback()
            return None

    async def list_by_camera(self, camera_id: uuid.UUID) -> list[CameraSubsystemHealth]:
        """Every health row for one camera, across every subsystem that has
        ever reported on it -- used by ``CameraRegistryService.delete()`` to
        clean this ephemeral runtime bookkeeping up before deleting the
        camera itself. Not evidence: a health tick, re-created automatically
        the moment a subsystem next reports on a re-registered camera."""
        result = await self._session.execute(
            select(CameraSubsystemHealth).where(CameraSubsystemHealth.camera_id == camera_id)
        )
        return list(result.scalars().all())
