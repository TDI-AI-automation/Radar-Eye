"""Tests for apps.deepstream.app.instrumentation.PerformanceInstrumentation.

No pyds/Gst dependency. System-level sampling (GPU/CPU/memory) is exercised
by monkeypatching the module's own read functions rather than depending on
real hardware/subprocess output -- RM-11 Phase 1's instrumentation
requirement, isolated from environment specifics.
"""

from __future__ import annotations

import pytest

from apps.deepstream.app import instrumentation as instrumentation_module
from apps.deepstream.app.instrumentation import PerformanceInstrumentation, _ProcStatSample


class _FakeClock:
    """Deterministic stand-in for time.monotonic()."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(instrumentation_module.time, "monotonic", fake)
    return fake


class TestPipelineStartup:
    def test_no_marks_yields_none(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        assert instrumentation.snapshot().pipeline_startup_seconds is None

    def test_startup_seconds_is_delta_between_marks(self, clock: _FakeClock) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.mark_pipeline_build_start()
        clock.advance(3.5)
        instrumentation.mark_pipeline_playing()

        assert instrumentation.snapshot().pipeline_startup_seconds == pytest.approx(3.5)


class TestFrameRecording:
    def test_first_frame_after_playing_sets_pgie_init_seconds(self, clock: _FakeClock) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.mark_pipeline_build_start()
        clock.advance(1.0)
        instrumentation.mark_pipeline_playing()
        clock.advance(2.0)

        instrumentation.record_frame(ingress_seconds=clock(), metadata_seconds=clock())

        assert instrumentation.snapshot().pgie_init_seconds == pytest.approx(2.0)

    def test_pgie_init_seconds_only_set_once(self, clock: _FakeClock) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.mark_pipeline_playing()
        clock.advance(1.0)
        instrumentation.record_frame(ingress_seconds=clock(), metadata_seconds=clock())
        clock.advance(5.0)
        instrumentation.record_frame(ingress_seconds=clock(), metadata_seconds=clock())

        assert instrumentation.snapshot().pgie_init_seconds == pytest.approx(1.0)

    def test_latency_ms_from_ingress_to_metadata_single_sample(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.record_frame(ingress_seconds=10.0, metadata_seconds=10.025)

        assert instrumentation.snapshot().end_to_end_latency_ms == pytest.approx(25.0)

    def test_latency_ms_is_a_rolling_average_not_the_last_sample(self) -> None:
        """RM-11 Phase 2 Principal Engineer review's latency-instrumentation
        follow-up: a real-hardware diagnostic confirmed the ingress/egress
        buffer correlation itself is reliable (PTS-verified, 15/15 matches);
        the actual defect was reporting only the single most-recent sample,
        which is highly sensitive to exactly when snapshot() happens to be
        called (e.g. during a startup transient vs. steady state)."""
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.record_frame(ingress_seconds=0.0, metadata_seconds=0.120)  # 120ms
        instrumentation.record_frame(ingress_seconds=1.0, metadata_seconds=1.002)  # 2ms
        instrumentation.record_frame(ingress_seconds=2.0, metadata_seconds=2.002)  # 2ms

        # Average of [120, 2, 2] ms, not just the last (2ms).
        assert instrumentation.snapshot().end_to_end_latency_ms == pytest.approx(
            (120.0 + 2.0 + 2.0) / 3, rel=1e-6
        )

    def test_latency_window_evicts_oldest_samples_once_full(self) -> None:
        """The window is bounded (not an ever-growing/all-time average) --
        entirely fresh samples eventually push every old sample out."""
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        window_size = instrumentation._latency_samples_ms.maxlen  # noqa: SLF001
        assert window_size is not None

        for i in range(window_size):
            instrumentation.record_frame(ingress_seconds=float(i), metadata_seconds=float(i) + 0.1)
        assert instrumentation.snapshot().end_to_end_latency_ms == pytest.approx(100.0, rel=1e-3)

        # A full window's worth of new, much lower-latency samples --
        # every original 100ms sample has now been evicted.
        for i in range(window_size):
            t = 1000.0 + i
            instrumentation.record_frame(ingress_seconds=t, metadata_seconds=t + 0.001)

        assert instrumentation.snapshot().end_to_end_latency_ms == pytest.approx(1.0, rel=1e-3)

    def test_frames_processed_increments(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.record_frame(ingress_seconds=0.0, metadata_seconds=0.01)
        instrumentation.record_frame(ingress_seconds=0.1, metadata_seconds=0.11)

        assert instrumentation.snapshot().frames_processed == 2

    def test_fps_requires_at_least_two_frames(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        assert instrumentation.snapshot().inference_fps is None

        instrumentation.record_frame(ingress_seconds=0.0, metadata_seconds=0.0)
        assert instrumentation.snapshot().inference_fps is None

    def test_fps_computed_from_frame_interval(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        # 10 frames exactly 0.1s apart -> 10 fps.
        for i in range(10):
            t = i * 0.1
            instrumentation.record_frame(ingress_seconds=t, metadata_seconds=t)

        assert instrumentation.snapshot().inference_fps == pytest.approx(10.0, rel=0.01)

    def test_pgie_is_placeholder_carried_through_to_snapshot(self) -> None:
        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        assert instrumentation.snapshot().pgie_is_placeholder is True

        instrumentation2 = PerformanceInstrumentation(pgie_is_placeholder=False)
        assert instrumentation2.snapshot().pgie_is_placeholder is False


class TestSystemMetricsSampling:
    def test_gpu_metrics_populated_from_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            instrumentation_module, "_read_gpu_metrics", lambda: (55.0, 1024.0, 12288.0)
        )
        monkeypatch.setattr(instrumentation_module, "_read_proc_stat", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_system_memory_used_pct", lambda: None)

        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.sample_system_metrics()

        snapshot = instrumentation.snapshot()
        assert snapshot.gpu_utilization_pct == 55.0
        assert snapshot.gpu_memory_used_mb == 1024.0
        assert snapshot.gpu_memory_total_mb == 12288.0

    def test_gpu_metrics_unavailable_leaves_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(instrumentation_module, "_read_gpu_metrics", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_proc_stat", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_system_memory_used_pct", lambda: None)

        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.sample_system_metrics()

        assert instrumentation.snapshot().gpu_utilization_pct is None

    def test_cpu_utilization_needs_two_samples(self, monkeypatch: pytest.MonkeyPatch) -> None:
        samples = iter([_ProcStatSample(idle=100, total=200), _ProcStatSample(idle=150, total=300)])
        monkeypatch.setattr(instrumentation_module, "_read_gpu_metrics", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_proc_stat", lambda: next(samples))
        monkeypatch.setattr(instrumentation_module, "_read_system_memory_used_pct", lambda: None)

        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.sample_system_metrics()
        assert instrumentation.snapshot().cpu_utilization_pct is None

        instrumentation.sample_system_metrics()
        # idle_delta=50, total_delta=100 -> 50% busy
        assert instrumentation.snapshot().cpu_utilization_pct == pytest.approx(50.0)

    def test_system_memory_used_pct_populated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(instrumentation_module, "_read_gpu_metrics", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_proc_stat", lambda: None)
        monkeypatch.setattr(instrumentation_module, "_read_system_memory_used_pct", lambda: 42.5)

        instrumentation = PerformanceInstrumentation(pgie_is_placeholder=True)
        instrumentation.sample_system_metrics()

        assert instrumentation.snapshot().system_memory_used_pct == 42.5
