"""Tests for manager.py -- RM-11.SIV visualization subsystem.

Covers only the GStreamer/pyds-independent orchestration surface (health()
state transitions, safe no-ops before initialize()) -- initialize() itself
requires real gi/Gst and is hardware-verified instead, per this repo's
established convention (no test file in this directory imports pyds or
gi -- see runtime_adapter.py's extraction code for the same split).
"""

from __future__ import annotations

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
