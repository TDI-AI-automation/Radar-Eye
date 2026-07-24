"""Tests for manager.py -- RM-11.SIV visualization subsystem.

Covers only the GStreamer/pyds-independent orchestration surface (health()
state transitions, safe no-ops before initialize()) -- initialize() itself
requires real gi/Gst and is hardware-verified instead, per this repo's
established convention (no test file in this directory imports pyds or
gi -- see runtime_adapter.py's extraction code for the same split).
"""

from __future__ import annotations

from typing import Any

from apps.deepstream.app.config import VisualizationSettings
from apps.deepstream.app.visualization.manager import VisualizationManager
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry


def test_health_reports_disabled_when_settings_disabled() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=False))

    health = manager.health()

    assert health.enabled is False
    assert health.running is False
    assert health.reason is None


def test_health_reports_enabled_not_running_before_initialize() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    health = manager.health()

    assert health.enabled is True
    assert health.running is False
    assert health.reason is None


def test_mark_failed_surfaces_reason_and_keeps_running_false() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    manager.mark_failed("Failed to create nvv4l2h264enc")

    health = manager.health()
    assert health.enabled is True
    assert health.running is False
    assert health.reason == "Failed to create nvv4l2h264enc"


def test_disabled_health_ignores_a_prior_mark_failed() -> None:
    """settings.enabled is the authoritative "intentionally disabled"
    signal -- a stale failure reason from a previous session must never
    leak into the disabled state's reporting."""
    manager = VisualizationManager(VisualizationSettings(enabled=False))
    manager.mark_failed("stale reason")

    health = manager.health()
    assert health.enabled is False
    assert health.running is False


def test_track_annotations_is_available_before_initialize() -> None:
    manager = VisualizationManager(VisualizationSettings())

    assert isinstance(manager.track_annotations, TrackAnnotationRegistry)


def test_start_before_initialize_is_a_safe_noop() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    manager.start()

    assert manager.health().running is False


def test_stop_before_initialize_is_safe() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    manager.stop()  # must not raise

    assert manager.health().running is False


def test_stop_is_safe_to_call_repeatedly() -> None:
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    manager.stop()
    manager.stop()
    manager.stop()

    assert manager.health().running is False


class _FakePipelineBuilder:
    """Test double standing in for a real (gi/Gst-dependent)
    VisualizationPipelineBuilder -- just enough to prove mark_failed()
    calls teardown() with the pipeline it was given, without needing
    real GStreamer."""

    def __init__(self) -> None:
        self.teardown_calls: list[Any] = []

    def teardown(self, pipeline: Any) -> None:
        self.teardown_calls.append(pipeline)


class _RaisingPipelineBuilder:
    def teardown(self, pipeline: Any) -> None:
        raise RuntimeError("teardown blew up too")


def test_mark_failed_tears_down_a_partially_built_pipeline() -> None:
    """Code-review finding (PR #8): mark_failed() must not just drop its
    references to whatever initialize()/start() already built into the
    live pipeline -- it must tear it down first, the same way stop()
    does, or the visualization branch keeps running (reaching PLAYING
    with the rest of the pipeline, still encoding/publishing) even
    though health() reports it as failed."""
    manager = VisualizationManager(VisualizationSettings(enabled=True))
    fake_builder = _FakePipelineBuilder()
    fake_pipeline = object()
    manager._pipeline_builder = fake_builder  # type: ignore[assignment]
    manager._pipeline = fake_pipeline

    manager.mark_failed("Failed to attach RTSP server on port 8554")

    assert fake_builder.teardown_calls == [fake_pipeline]
    health = manager.health()
    assert health.running is False
    assert health.reason == "Failed to attach RTSP server on port 8554"


def test_mark_failed_without_a_prior_initialize_does_not_attempt_teardown() -> None:
    """No pipeline_builder/pipeline ever got set (initialize() itself
    failed before assigning them, or was never called) -- mark_failed()
    must not call teardown() on nothing."""
    manager = VisualizationManager(VisualizationSettings(enabled=True))

    manager.mark_failed("Failed to create nvv4l2h264enc")  # must not raise

    assert manager.health().running is False


def test_mark_failed_never_raises_even_if_teardown_itself_fails() -> None:
    """mark_failed() is called from inside builder.py's own except block,
    with no further try/except around it -- if it ever raised, camera
    setup would crash, defeating the whole point of failure isolation.
    Cleanup is best-effort: the original failure reason must still win."""
    manager = VisualizationManager(VisualizationSettings(enabled=True))
    manager._pipeline_builder = _RaisingPipelineBuilder()  # type: ignore[assignment]
    manager._pipeline = object()

    manager.mark_failed("original failure reason")  # must not raise

    health = manager.health()
    assert health.running is False
    assert health.reason == "original failure reason"
