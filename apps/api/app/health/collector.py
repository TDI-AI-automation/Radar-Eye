"""Health metrics collector module.

Source: docs/IMPLEMENTATION_ROADMAP.md — RM-09 Health & Monitoring.
Collects GPU metrics, disk storage space, camera stream frame rates, frame age,
and stalled stream detection.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from shared.schemas.camera import CameraConnectionStatus, CameraHealthSchema
from shared.schemas.health import (
    CameraHealthSummarySchema,
    GPUHealthSchema,
    HealthStatus,
    StorageHealthSchema,
    SystemHealthSchema,
)

logger = logging.getLogger(__name__)


class HealthCollector:
    """In-memory metrics collector for lightweight health monitoring inside apps.api.

    Tracks camera stream heartbeats, computes FPS/last-frame-age, detects stalled
    streams, inspects storage utilization, and queries GPU metrics where available.
    """

    def __init__(
        self,
        stalled_threshold_seconds: float = 5.0,
        default_storage_path: str = "./storage",
    ) -> None:
        self.stalled_threshold_seconds = stalled_threshold_seconds
        self.default_storage_path = default_storage_path
        self._camera_heartbeats: dict[uuid.UUID, dict[str, Any]] = {}

    def record_camera_heartbeat(
        self,
        camera_id: uuid.UUID,
        status: CameraConnectionStatus = "CONNECTED",
        fps: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Record or update heartbeat and decoded FPS for a specific camera."""
        now = timestamp or datetime.now(timezone.utc)
        self._camera_heartbeats[camera_id] = {
            "status": status,
            "fps": fps,
            "last_seen": now,
        }

    def get_camera_health(
        self,
        camera_id: uuid.UUID,
        default_status: CameraConnectionStatus = "DISCONNECTED",
        now: datetime | None = None,
    ) -> CameraHealthSchema:
        """Return current health metrics for a single camera."""
        record = self._camera_heartbeats.get(camera_id)
        if not record:
            return CameraHealthSchema(
                camera_id=camera_id,
                status=default_status,
                fps=None,
                last_frame_age_seconds=None,
            )

        current_time = now or datetime.now(timezone.utc)
        last_seen: datetime = record["last_seen"]
        age_seconds = max(0.0, (current_time - last_seen).total_seconds())

        return CameraHealthSchema(
            camera_id=camera_id,
            status=record["status"],
            fps=record["fps"] if record["status"] == "CONNECTED" else None,
            last_frame_age_seconds=(
                round(age_seconds, 2) if record["status"] == "CONNECTED" else None
            ),
        )

    def get_camera_health_summary(
        self,
        registered_camera_ids: list[uuid.UUID] | None = None,
        now: datetime | None = None,
    ) -> CameraHealthSummarySchema:
        """Summarize camera status counts across all registered or active cameras."""
        current_time = now or datetime.now(timezone.utc)

        # Merge registered IDs with active heartbeats
        all_ids: set[uuid.UUID] = set(self._camera_heartbeats.keys())
        if registered_camera_ids:
            all_ids.update(registered_camera_ids)

        total = len(all_ids)
        connected = 0
        disconnected = 0
        reconnecting = 0
        stalled = 0

        for cam_id in all_ids:
            health = self.get_camera_health(cam_id, now=current_time)
            if health.status == "CONNECTED":
                connected += 1
                if (
                    health.last_frame_age_seconds is not None
                    and health.last_frame_age_seconds > self.stalled_threshold_seconds
                ):
                    stalled += 1
            elif health.status == "RECONNECTING":
                reconnecting += 1
            else:
                disconnected += 1

        return CameraHealthSummarySchema(
            total_cameras=total,
            connected_count=connected,
            disconnected_count=disconnected,
            reconnecting_count=reconnecting,
            stalled_count=stalled,
        )

    def detect_stalled_cameras(
        self,
        max_age_seconds: float | None = None,
        now: datetime | None = None,
    ) -> list[uuid.UUID]:
        """Identify camera IDs marked CONNECTED whose frame age exceeds threshold."""
        threshold = (
            max_age_seconds if max_age_seconds is not None else self.stalled_threshold_seconds
        )
        current_time = now or datetime.now(timezone.utc)
        stalled: list[uuid.UUID] = []

        for cam_id, record in self._camera_heartbeats.items():
            if record["status"] == "CONNECTED":
                age = (current_time - record["last_seen"]).total_seconds()
                if age > threshold:
                    stalled.append(cam_id)

        return stalled

    def get_storage_health(self, path: str | None = None) -> StorageHealthSchema:
        """Query storage capacity and usage for the given directory path."""
        target_path = path or self.default_storage_path

        # Fallback to current working directory if target_path does not exist
        check_path = target_path if os.path.exists(target_path) else "."

        total, used, free = shutil.disk_usage(check_path)
        usage_pct = (used / total * 100.0) if total > 0 else 0.0

        return StorageHealthSchema(
            path=target_path,
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            usage_percent=round(usage_pct, 2),
        )

    def get_gpu_health(self) -> GPUHealthSchema:
        """Query GPU health parameters (utilization, memory, temperature).

        Attempts to query NVIDIA NVML or tegrastats. Returns fallback None fields
        when running on CPU-only or non-NVIDIA developer environments.
        """
        # Try pynvml / NVML if installed
        try:
            import pynvml  # type: ignore[import-not-found]

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            pynvml.nvmlShutdown()

            return GPUHealthSchema(
                utilization_percent=float(util.gpu),
                memory_used_mb=round(mem.used / (1024 * 1024), 2),
                memory_total_mb=round(mem.total / (1024 * 1024), 2),
                temperature_celsius=float(temp),
            )
        except Exception:
            pass

        # Fallback for non-Jetson / dev environments
        return GPUHealthSchema(
            utilization_percent=None,
            memory_used_mb=None,
            memory_total_mb=None,
            temperature_celsius=None,
        )

    def get_system_health(
        self,
        db_healthy: bool = True,
        bus_healthy: bool = True,
        registered_camera_ids: list[uuid.UUID] | None = None,
        storage_path: str | None = None,
        now: datetime | None = None,
    ) -> SystemHealthSchema:
        """Aggregate health metrics across storage, GPU, cameras, and core components."""
        current_time = now or datetime.now(timezone.utc)
        gpu = self.get_gpu_health()
        storage = self.get_storage_health(storage_path)
        cameras = self.get_camera_health_summary(
            registered_camera_ids=registered_camera_ids, now=current_time
        )

        db_status = "healthy" if db_healthy else "unhealthy"
        bus_status = "healthy" if bus_healthy else "unhealthy"

        components = {
            "database": db_status,
            "event_bus": bus_status,
            "gpu": "healthy" if gpu.utilization_percent is not None else "unavailable",
            "storage": (
                "unhealthy"
                if storage.usage_percent > 95.0
                else ("degraded" if storage.usage_percent > 85.0 else "healthy")
            ),
            "cameras": (
                "degraded"
                if cameras.disconnected_count > 0 or cameras.stalled_count > 0
                else "healthy"
            ),
        }

        # Overall health status determination
        if not db_healthy or not bus_healthy or storage.usage_percent > 95.0:
            overall_status: HealthStatus = "unhealthy"
        elif (
            cameras.disconnected_count > 0
            or cameras.stalled_count > 0
            or storage.usage_percent > 85.0
        ):
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return SystemHealthSchema(
            status=overall_status,
            timestamp=current_time,
            gpu=gpu,
            storage=storage,
            cameras=cameras,
            components=components,
        )
