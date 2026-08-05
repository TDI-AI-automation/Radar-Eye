"""Tests for apps.api.app.repositories.media -- the Media Distribution
Interface's cross-process tables (ADR-028). Both repositories' set_*
methods are upserts; these tests exercise exactly that contract.
"""

from __future__ import annotations

import pytest

from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.media import (
    CameraMediaEndpointRepository,
    CameraSubsystemHealthRepository,
)


async def _make_camera(session, name: str = "cam-1") -> Camera:
    camera = Camera(name=name, location="north gate", status="CONNECTED")
    return await CameraRepository(session).add(camera)


@pytest.mark.asyncio
class TestCameraMediaEndpointRepository:
    async def test_set_endpoint_creates_a_new_row(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraMediaEndpointRepository(db_session)

        endpoint = await repo.set_endpoint(
            camera.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/x"
        )

        assert endpoint.camera_id == camera.id
        assert endpoint.subsystem == "ingestion"
        assert endpoint.transport == "rtsp"
        assert endpoint.address == "rtsp://127.0.0.1:8600/x"

    async def test_set_endpoint_is_an_upsert(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraMediaEndpointRepository(db_session)

        await repo.set_endpoint(
            camera.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/first"
        )
        await repo.set_endpoint(
            camera.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/second"
        )

        rows = await repo.list()
        matching = [
            row for row in rows if row.camera_id == camera.id and row.subsystem == "ingestion"
        ]
        assert len(matching) == 1
        assert matching[0].address == "rtsp://127.0.0.1:8600/second"

    async def test_different_subsystems_get_independent_rows(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraMediaEndpointRepository(db_session)

        await repo.set_endpoint(
            camera.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/raw"
        )
        await repo.set_endpoint(
            camera.id, "ai", transport="rtsp", address="rtsp://127.0.0.1:8601/annotated"
        )

        raw = await repo.get_by_camera_and_subsystem(camera.id, "ingestion")
        ai = await repo.get_by_camera_and_subsystem(camera.id, "ai")
        assert raw is not None and raw.address == "rtsp://127.0.0.1:8600/raw"
        assert ai is not None and ai.address == "rtsp://127.0.0.1:8601/annotated"

    async def test_delete_endpoint_is_idempotent(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraMediaEndpointRepository(db_session)
        await repo.set_endpoint(
            camera.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/x"
        )

        await repo.delete_endpoint(camera.id, "ingestion")
        await repo.delete_endpoint(camera.id, "ingestion")  # must not raise

        assert await repo.get_by_camera_and_subsystem(camera.id, "ingestion") is None

    async def test_list_by_subsystem_returns_only_that_subsystems_rows(self, db_session) -> None:
        camera_a = await _make_camera(db_session, "cam-a")
        camera_b = await _make_camera(db_session, "cam-b")
        repo = CameraMediaEndpointRepository(db_session)
        await repo.set_endpoint(
            camera_a.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/a"
        )
        await repo.set_endpoint(
            camera_b.id, "ingestion", transport="rtsp", address="rtsp://127.0.0.1:8600/b"
        )
        await repo.set_endpoint(
            camera_a.id, "ai", transport="rtsp", address="rtsp://127.0.0.1:8601/a"
        )

        rows = await repo.list_by_subsystem("ingestion")

        assert {row.camera_id for row in rows} == {camera_a.id, camera_b.id}
        assert all(row.subsystem == "ingestion" for row in rows)

    async def test_list_by_subsystem_empty_when_none_published(self, db_session) -> None:
        repo = CameraMediaEndpointRepository(db_session)
        assert await repo.list_by_subsystem("ingestion") == []


@pytest.mark.asyncio
class TestCameraSubsystemHealthRepository:
    async def test_set_health_creates_a_new_row(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraSubsystemHealthRepository(db_session)

        health = await repo.set_health(camera.id, "ingestion", status="RECONNECTING")

        assert health.camera_id == camera.id
        assert health.subsystem == "ingestion"
        assert health.status == "RECONNECTING"
        assert health.detail is None

    async def test_set_health_is_an_upsert(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraSubsystemHealthRepository(db_session)

        await repo.set_health(camera.id, "ingestion", status="RECONNECTING")
        await repo.set_health(camera.id, "ingestion", status="CONNECTED")

        rows = await repo.list()
        matching = [
            row for row in rows if row.camera_id == camera.id and row.subsystem == "ingestion"
        ]
        assert len(matching) == 1
        assert matching[0].status == "CONNECTED"

    async def test_different_subsystems_get_independent_rows(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = CameraSubsystemHealthRepository(db_session)

        await repo.set_health(camera.id, "ingestion", status="CONNECTED")
        await repo.set_health(camera.id, "ai", status="DISCONNECTED", detail="model not loaded")

        ingestion = await repo.get_by_camera_and_subsystem(camera.id, "ingestion")
        ai = await repo.get_by_camera_and_subsystem(camera.id, "ai")
        assert ingestion is not None and ingestion.status == "CONNECTED"
        assert ai is not None and ai.status == "DISCONNECTED" and ai.detail == "model not loaded"
