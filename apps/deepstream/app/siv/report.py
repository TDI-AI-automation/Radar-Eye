"""Automatic SIV report generator -- RM-11.SIV "Automatic SIV Report" requirement.

Writes ``siv_reports/siv_report_<timestamp>.json`` (plus a
``siv_report_latest.json`` convenience pointer) after each validation run,
summarizing the final ``HeartbeatRegistry``/``PerformanceInstrumentation``
state -- the same two objects the watchdog and dashboard already read from
(Unified Heartbeat's single source of truth). This becomes the baseline
artifact the roadmap's 1 -> 2 -> 4 -> 8 -> 10 -> 20-camera scaling
comparisons (RM-11 Phase 3+) will diff future runs against.

Pure data -- ``build_report`` takes no I/O dependency and is fully unit
testable; ``write_report``/``generate_siv_report`` are the only functions
that touch the filesystem.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORTS_DIR = REPO_ROOT / "siv_reports"

_HEARTBEAT_COMPONENTS = (
    "camera",
    "rtsp",
    "pgie",
    "tracker",
    "sgie",
    "runtime_adapter",
    "threat_runtime_adapter",
    "threat_engine",
    "calibration",
    "incident",
    "alarm",
    "event_bus",
    "heartbeat",
)


def build_report(
    *,
    heartbeat_registry: HeartbeatRegistry,
    instrumentation: PerformanceInstrumentation,
    watchdog_settings: WatchdogSettings,
) -> dict:
    snapshot = instrumentation.snapshot()
    thresholds = watchdog_settings.stale_after_seconds

    components = {}
    for name in _HEARTBEAT_COMPONENTS:
        status = heartbeat_registry.status(name, stale_after_seconds=getattr(thresholds, name))
        components[name] = {
            "healthy": status.healthy,
            "counter": status.counter,
            "reason": status.reason,
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline": {
            "fps": snapshot.inference_fps,
            "pgie_fps": snapshot.pgie_fps,
            "sgie_fps": snapshot.sgie_fps,
            "latency_ms": snapshot.end_to_end_latency_ms,
            "frames_processed": snapshot.frames_processed,
            "pgie_is_placeholder": snapshot.pgie_is_placeholder,
        },
        "system": {
            "gpu_utilization_pct": snapshot.gpu_utilization_pct,
            "gpu_memory_used_mb": snapshot.gpu_memory_used_mb,
            "gpu_memory_total_mb": snapshot.gpu_memory_total_mb,
            "cpu_utilization_pct": snapshot.cpu_utilization_pct,
            "system_memory_used_pct": snapshot.system_memory_used_pct,
        },
        "throughput": {
            "event_per_sec": snapshot.event_throughput_per_sec,
            "threat_per_sec": snapshot.threat_throughput_per_sec,
            "alarm_per_sec": snapshot.alarm_throughput_per_sec,
            "incident_per_sec": snapshot.incident_throughput_per_sec,
        },
        # Counts (as opposed to throughput above) double as this report's
        # "Validation Results" -- healthy=True across every component,
        # counters > 0 where the checklist expects activity, is the
        # machine-checkable half of docs/SIV_VALIDATION_REPORT.md.
        "components": components,
    }


def write_report(report: dict, *, reports_dir: Path | None = None) -> Path:
    directory = reports_dir or DEFAULT_REPORTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    timestamp_slug = report["timestamp"].replace(":", "").replace("+00:00", "Z")
    path = directory / f"siv_report_{timestamp_slug}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest = directory / "siv_report_latest.json"
    latest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def generate_siv_report(
    *,
    heartbeat_registry: HeartbeatRegistry,
    instrumentation: PerformanceInstrumentation,
    watchdog_settings: WatchdogSettings,
    reports_dir: Path | None = None,
) -> Path:
    report = build_report(
        heartbeat_registry=heartbeat_registry,
        instrumentation=instrumentation,
        watchdog_settings=watchdog_settings,
    )
    return write_report(report, reports_dir=reports_dir)
