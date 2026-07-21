"""Unit and API integration tests for RM-09 Health & Monitoring.

Source: docs/IMPLEMENTATION_ROADMAP.md — RM-09.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.app.health import HealthCollector
from apps.api.app.main import create_app
from shared.schemas.health import (
    CameraHealthSummarySchema,
    GPUHealthSchema,
    StorageHealthSchema,
    SystemHealthSchema,
)


def test_gpu_health_fallback() -> None:
    """Test that GPU health query returns a valid schema even when NVML is absent."""
    collector = HealthCollector()
    gpu = collector.get_gpu_health()
    assert isinstance(gpu, GPUHealthSchema)


def test_storage_health() -> None:
    """Test storage capacity and usage query."""
    collector = HealthCollector()
    storage = collector.get_storage_health()
    assert isinstance(storage, StorageHealthSchema)
    assert storage.total_bytes > 0
    assert storage.free_bytes >= 0
    assert 0.0 <= storage.usage_percent <= 100.0


def test_camera_heartbeat_and_health() -> None:
    """Test camera heartbeat recording, frame age calculation, and status query."""
    collector = HealthCollector(stalled_threshold_seconds=5.0)
    cam_id = uuid.uuid4()

    # Initial state — unrecorded camera
    unrec = collector.get_camera_health(cam_id)
    assert unrec.status == "DISCONNECTED"
    assert unrec.fps is None
    assert unrec.last_frame_age_seconds is None

    # Record heartbeat
    now = datetime.now(timezone.utc)
    collector.record_camera_heartbeat(cam_id, status="CONNECTED", fps=29.8, timestamp=now)

    health = collector.get_camera_health(cam_id, now=now + timedelta(seconds=2.0))
    assert health.status == "CONNECTED"
    assert health.fps == 29.8
    assert health.last_frame_age_seconds == 2.0


def test_stalled_camera_detection() -> None:
    """Test detection of stalled-but-alive camera video streams."""
    collector = HealthCollector(stalled_threshold_seconds=5.0)
    cam_normal = uuid.uuid4()
    cam_stalled = uuid.uuid4()

    now = datetime.now(timezone.utc)
    collector.record_camera_heartbeat(cam_normal, status="CONNECTED", fps=30.0, timestamp=now)
    collector.record_camera_heartbeat(
        cam_stalled,
        status="CONNECTED",
        fps=30.0,
        timestamp=now - timedelta(seconds=10.0),
    )

    stalled = collector.detect_stalled_cameras(now=now)
    assert cam_stalled in stalled
    assert cam_normal not in stalled

    summary = collector.get_camera_health_summary(now=now)
    assert isinstance(summary, CameraHealthSummarySchema)
    assert summary.connected_count == 2
    assert summary.stalled_count == 1


def test_system_health_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test aggregated system health calculation."""
    collector = HealthCollector()
    now = datetime.now(timezone.utc)

    # Mock storage health to 50% usage for clean healthy baseline
    monkeypatch.setattr(
        collector,
        "get_storage_health",
        lambda path=None: StorageHealthSchema(
            path="./storage",
            total_bytes=100_000_000_000,
            used_bytes=50_000_000_000,
            free_bytes=50_000_000_000,
            usage_percent=50.0,
        ),
    )

    # Healthy state
    sys_health = collector.get_system_health(db_healthy=True, bus_healthy=True, now=now)
    assert isinstance(sys_health, SystemHealthSchema)
    assert sys_health.status == "healthy"
    assert sys_health.components["database"] == "healthy"
    assert sys_health.components["event_bus"] == "healthy"

    # Degraded state (stalled camera)
    cam_stalled = uuid.uuid4()
    collector.record_camera_heartbeat(
        cam_stalled,
        status="CONNECTED",
        fps=30.0,
        timestamp=now - timedelta(seconds=10.0),
    )
    sys_degraded = collector.get_system_health(db_healthy=True, bus_healthy=True, now=now)
    assert sys_degraded.status == "degraded"

    # Unhealthy state (DB failure)
    sys_unhealthy = collector.get_system_health(db_healthy=False, bus_healthy=True, now=now)
    assert sys_unhealthy.status == "unhealthy"


@pytest.mark.asyncio
async def test_health_rest_endpoints(_default_env: None) -> None:
    """Test REST API responses for /api/v1/health/* and /api/v1/cameras/{id}/health."""
    app = create_app()
    cam_id = uuid.uuid4()

    # Pre-populate heartbeat
    collector: HealthCollector = app.state.health_collector
    collector.record_camera_heartbeat(cam_id, status="CONNECTED", fps=30.0)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # GET /api/v1/health/system
        resp = await client.get("/api/v1/health/system")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "status" in body["data"]

        # GET /api/v1/health/gpu
        resp = await client.get("/api/v1/health/gpu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        # GET /api/v1/health/storage
        resp = await client.get("/api/v1/health/storage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "usage_percent" in body["data"]

        # GET /api/v1/health/cameras
        resp = await client.get("/api/v1/health/cameras")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1

        # GET /api/v1/cameras/{camera_id}/health
        resp = await client.get(f"/api/v1/cameras/{cam_id}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["camera_id"] == str(cam_id)
        assert body["data"]["status"] == "CONNECTED"
        assert body["data"]["fps"] == 30.0
