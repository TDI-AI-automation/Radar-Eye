"""Console validation dashboard -- RM-11.SIV Task 8.

Reads the exact same ``HeartbeatRegistry`` the watchdog reads from (Unified
Heartbeat requirement -- one source of truth) plus a
``PerformanceInstrumentation`` snapshot, and renders a plain-text status
table. Deliberately more than healthy/unhealthy per component (FPS,
throughput, last-activity age) -- "operationally useful", per the approval.

``render()`` is a pure function of current state (no I/O) so it can be unit
tested directly; ``run_forever`` is the only piece that actually writes to
the terminal, driven by ``scripts/run_siv.py``.
"""

from __future__ import annotations

import asyncio

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry, HeartbeatStatus
from apps.deepstream.app.instrumentation import PerformanceInstrumentation, PerformanceSnapshot

_CLEAR_SCREEN = "\033[2J\033[H"

_MARK_ALIVE = "✓"  # check mark
_MARK_STALLED = "✗"  # cross mark


class Dashboard:
    def __init__(
        self,
        *,
        heartbeat_registry: HeartbeatRegistry,
        instrumentation: PerformanceInstrumentation,
        settings: WatchdogSettings,
    ) -> None:
        self._heartbeat = heartbeat_registry
        self._instrumentation = instrumentation
        self._settings = settings

    def _status(self, component: str) -> HeartbeatStatus:
        threshold = getattr(self._settings.stale_after_seconds, component)
        return self._heartbeat.status(component, stale_after_seconds=threshold)

    @staticmethod
    def _fmt(value: float | None, suffix: str = "") -> str:
        return f"{value:.1f}{suffix}" if value is not None else "n/a"

    def _stage_block(
        self, title: str, component: str, extra: dict[str, str] | None = None
    ) -> list[str]:
        status = self._status(component)
        mark = _MARK_ALIVE if status.healthy else _MARK_STALLED
        state = "Alive" if status.healthy else "STALLED"
        age = status.age_seconds()
        lines = [
            title,
            f"  {mark} {state}  (count={status.counter}, last activity {age:.1f}s ago)",
        ]
        if not status.healthy and status.reason:
            lines.append(f"  reason: {status.reason}")
        for label, value in (extra or {}).items():
            lines.append(f"  {label}: {value}")
        return lines

    def render(self) -> str:
        snapshot: PerformanceSnapshot = self._instrumentation.snapshot()
        lines: list[str] = []
        lines.append("=" * 64)
        lines.append("RADAR EYE -- RM-11.SIV SYSTEM INTEGRATION VALIDATION DASHBOARD")
        lines.append("=" * 64)

        lines += self._stage_block(
            "Pipeline",
            "pipeline_fps",
            {"Pipeline FPS": self._fmt(snapshot.inference_fps)},
        )
        lines += self._stage_block("Camera", "camera")
        lines += self._stage_block("RTSP", "rtsp")
        lines += self._stage_block("PGIE", "pgie", {"PGIE FPS": self._fmt(snapshot.pgie_fps)})
        lines += self._stage_block("NvDCF (Tracker)", "tracker")
        lines += self._stage_block("SGIE", "sgie", {"SGIE FPS": self._fmt(snapshot.sgie_fps)})
        lines += self._stage_block("RuntimeAdapter", "runtime_adapter")
        lines += self._stage_block("ThreatEngineRuntimeAdapter", "threat_runtime_adapter")
        lines += self._stage_block("Calibration", "calibration")
        lines += self._stage_block(
            "ThreatEngine",
            "threat_engine",
            {"Threats/sec": self._fmt(snapshot.threat_throughput_per_sec)},
        )
        lines += self._stage_block(
            "Incident",
            "incident",
            {"Incidents/sec": self._fmt(snapshot.incident_throughput_per_sec)},
        )
        lines += self._stage_block(
            "Alarm", "alarm", {"Alarms/sec": self._fmt(snapshot.alarm_throughput_per_sec)}
        )
        lines += self._stage_block(
            "EventBus",
            "event_bus",
            {"Events/sec": self._fmt(snapshot.event_throughput_per_sec)},
        )
        lines += self._stage_block("Heartbeat", "heartbeat")

        lines.append("-" * 64)
        lines.append(f"Latency:  {self._fmt(snapshot.end_to_end_latency_ms, 'ms')}")
        gpu_mem_used = self._fmt(snapshot.gpu_memory_used_mb)
        gpu_mem_total = self._fmt(snapshot.gpu_memory_total_mb)
        lines.append(
            f"GPU:      {self._fmt(snapshot.gpu_utilization_pct, '%')}  "
            f"Mem: {gpu_mem_used}/{gpu_mem_total} MB"
        )
        lines.append(
            f"CPU:      {self._fmt(snapshot.cpu_utilization_pct, '%')}  "
            f"RAM: {self._fmt(snapshot.system_memory_used_pct, '%')}"
        )
        lines.append(
            "Model:    "
            + (
                "PLACEHOLDER (see configs/models.yaml)"
                if snapshot.pgie_is_placeholder
                else "PRODUCTION"
            )
        )
        lines.append(f"Frames processed: {snapshot.frames_processed}")
        lines.append("=" * 64)
        return "\n".join(lines)

    def print_once(self) -> None:
        print(self.render())  # noqa: T201 -- this class's entire purpose is terminal output

    async def run_forever(self, *, interval_seconds: float = 2.0) -> None:
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                print(_CLEAR_SCREEN, end="")  # noqa: T201
                self.print_once()
        except asyncio.CancelledError:
            pass
