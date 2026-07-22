"""Tests for siv/dashboard.py -- RM-11.SIV Validation Dashboard requirement.

render() is a pure function of HeartbeatRegistry/PerformanceInstrumentation
state -- no stdout capture needed, no DeepStream/GStreamer dependency.
"""

from __future__ import annotations

from apps.deepstream.app.config import WatchdogSettings
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.siv.dashboard import Dashboard


def _make_dashboard(
    *,
    heartbeat: HeartbeatRegistry | None = None,
    instrumentation: PerformanceInstrumentation | None = None,
) -> Dashboard:
    return Dashboard(
        heartbeat_registry=heartbeat or HeartbeatRegistry(),
        instrumentation=instrumentation or PerformanceInstrumentation(pgie_is_placeholder=True),
        settings=WatchdogSettings(),
    )


class TestRenderShowsMoreThanHealthyUnhealthy:
    def test_includes_every_named_stage(self) -> None:
        dashboard = _make_dashboard()
        output = dashboard.render()

        for stage in (
            "Pipeline",
            "Camera",
            "RTSP",
            "PGIE",
            "NvDCF (Tracker)",
            "SGIE",
            "RuntimeAdapter",
            "ThreatEngineRuntimeAdapter",
            "Calibration",
            "ThreatEngine",
            "Incident",
            "Alarm",
            "EventBus",
            "Heartbeat",
        ):
            assert stage in output

    def test_includes_fps_and_throughput_labels_not_just_status(self) -> None:
        dashboard = _make_dashboard()
        output = dashboard.render()

        assert "PGIE FPS" in output
        assert "SGIE FPS" in output
        assert "Threats/sec" in output
        assert "Alarms/sec" in output
        assert "Incidents/sec" in output
        assert "Events/sec" in output
        assert "Latency" in output
        assert "GPU" in output


class TestHealthyVsStalledMarkers:
    def test_unbeaten_component_shows_stalled_marker(self) -> None:
        dashboard = _make_dashboard()
        output = dashboard.render()

        pgie_line = next(
            line for line in output.splitlines() if "STALLED" in line and "count=0" in line
        )
        assert "✗" in pgie_line

    def test_beaten_component_shows_alive_marker(self) -> None:
        heartbeat = HeartbeatRegistry()
        heartbeat.beat("pgie")
        dashboard = _make_dashboard(heartbeat=heartbeat)

        output = dashboard.render()
        pgie_block = output.split("PGIE\n", 1)[1].splitlines()[0]

        assert "✓" in pgie_block
        assert "Alive" in pgie_block


class TestMetricsReflectSnapshot:
    def test_fps_values_appear_when_recorded(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=False)
        instrumentation.record_pgie_frame()
        instrumentation.record_pgie_frame()  # two samples needed for a rate
        dashboard = _make_dashboard(instrumentation=instrumentation)

        output = dashboard.render()

        assert "n/a" not in [
            line.split("PGIE FPS:")[1].strip()
            for line in output.splitlines()
            if "PGIE FPS:" in line
        ]

    def test_placeholder_model_is_labeled(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        dashboard = _make_dashboard(instrumentation=instrumentation)

        assert "PLACEHOLDER" in dashboard.render()

    def test_production_model_is_labeled(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=False)
        dashboard = _make_dashboard(instrumentation=instrumentation)

        assert "PRODUCTION" in dashboard.render()
