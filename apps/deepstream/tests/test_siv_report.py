"""Tests for siv/report.py -- RM-11.SIV Automatic SIV Report requirement."""

from __future__ import annotations

import json
from pathlib import Path

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.siv.report import build_report, generate_siv_report, write_report


class TestBuildReport:
    def test_includes_timestamp(self) -> None:
        report = build_report(
            heartbeat_registry=HeartbeatRegistry(),
            instrumentation=PerformanceInstrumentation(pgie_is_placeholder=True),
            watchdog_settings=WatchdogSettings(),
        )
        assert "timestamp" in report

    def test_includes_every_heartbeat_component(self) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        report = build_report(
            heartbeat_registry=heartbeat,
            instrumentation=PerformanceInstrumentation(pgie_is_placeholder=True),
            watchdog_settings=WatchdogSettings(),
        )

        assert report["components"]["pgie"]["healthy"] is True
        assert report["components"]["pgie"]["counter"] == 1
        assert report["components"]["camera"]["healthy"] is False

    def test_includes_pipeline_system_and_throughput_sections(self) -> None:
        report = build_report(
            heartbeat_registry=HeartbeatRegistry(),
            instrumentation=PerformanceInstrumentation(pgie_is_placeholder=False),
            watchdog_settings=WatchdogSettings(),
        )

        assert "fps" in report["pipeline"]
        assert "gpu_utilization_pct" in report["system"]
        assert "threat_per_sec" in report["throughput"]
        assert report["pipeline"]["pgie_is_placeholder"] is False


class TestWriteReport:
    def test_writes_timestamped_and_latest_files(self, tmp_path: Path) -> None:
        report = build_report(
            heartbeat_registry=HeartbeatRegistry(),
            instrumentation=PerformanceInstrumentation(pgie_is_placeholder=True),
            watchdog_settings=WatchdogSettings(),
        )

        path = write_report(report, reports_dir=tmp_path)

        assert path.is_file()
        latest = tmp_path / "siv_report_latest.json"
        assert latest.is_file()
        assert json.loads(latest.read_text(encoding="utf-8"))["timestamp"] == report["timestamp"]

    def test_generate_siv_report_end_to_end(self, tmp_path: Path) -> None:
        path = generate_siv_report(
            heartbeat_registry=HeartbeatRegistry(),
            instrumentation=PerformanceInstrumentation(pgie_is_placeholder=True),
            watchdog_settings=WatchdogSettings(),
            reports_dir=tmp_path,
        )

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert "components" in loaded
        assert "pipeline" in loaded
