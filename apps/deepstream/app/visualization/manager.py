"""VisualizationManager -- the single visualization subsystem boundary,
RM-11.SIV.

Owns ``VisualizationPipelineBuilder``, ``TrackAnnotationRegistry``, and (from
Phase 3) ``RtspStreamServer`` as internal collaborators -- nothing outside
this package touches those classes directly. ``apps/deepstream/app/
pipeline/builder.py`` and ``runtime.py`` only ever call the five members
exposed here: ``initialize()``, ``start()``, ``stop()``, ``health()``, and
the ``track_annotations`` accessor. Future additions (recording, snapshots,
WebRTC, HLS, web streaming) become internal additions to this package,
never touching the pipeline builder or ``runtime.py`` again.

Always constructed regardless of ``visualization.enabled`` (cheap -- no
GStreamer/pyds touched by ``__init__`` itself), so ``health()`` can always
report a meaningful status, including "intentionally disabled by config"
without needing a special "manager is None" case anywhere else. Only
``initialize()``/``start()`` (called by ``builder.py`` only when
``visualization.enabled`` is true) ever touch GStreamer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.deepstream.app.config import VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.stage_logging import get_stage_logger
from apps.deepstream.app.visualization.pipeline_builder import VisualizationPipelineBuilder
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

_logger = get_stage_logger("visualization")


@dataclass(frozen=True)
class VisualizationHealth:
    """``enabled=False, running=False`` means intentionally disabled by
    config. ``enabled=True, running=False`` means visualization was
    supposed to start and didn't -- ``reason`` carries why (the
    failure-isolation path in ``builder.py`` sets exactly this state)."""

    enabled: bool
    running: bool
    bound_port: int | None
    stream_name: str
    reason: str | None


class VisualizationManager:
    def __init__(self, settings: VisualizationSettings) -> None:
        self._settings = settings
        self._track_annotations = TrackAnnotationRegistry(
            ttl_seconds=settings.annotation_ttl_seconds
        )
        self._pipeline_builder: VisualizationPipelineBuilder | None = None
        self._pipeline: Any = None
        self._running = False
        self._reason: str | None = None

    @property
    def track_annotations(self) -> TrackAnnotationRegistry:
        """The only reason anything outside this package needs a reference
        into it -- given to ``ThreatEngineRuntimeAdapter`` so it can write
        calibration/threat-engine results the OSD renderer later reads."""
        return self._track_annotations

    def initialize(
        self,
        pipeline: Any,
        tee: Any,
        *,
        camera_id: uuid.UUID,
        camera_name: str,
        instrumentation: PerformanceInstrumentation | None = None,
    ) -> None:
        """Builds the visualization GStreamer branch off ``tee``. Raises on
        any construction/validation failure -- callers (``builder.py``) are
        expected to catch, log, and call ``mark_failed()`` (the shared
        failure-isolation path, see docs/DEEPSTREAM_PIPELINE_SPEC.md's
        Visualization Path section) rather than let it propagate further."""
        self._pipeline = pipeline
        self._pipeline_builder = VisualizationPipelineBuilder(
            self._settings,
            camera_id=camera_id,
            camera_name=camera_name,
            track_annotations=self._track_annotations,
            instrumentation=instrumentation,
        )
        self._pipeline_builder.build(pipeline, tee)
        self._reason = None

    def start(self) -> None:
        """No-op if ``initialize()`` was never called or failed (disabled,
        or the failure-isolation path already caught something) -- matches
        ``RtspStreamServer.start()``'s own None-safety, added in Phase 3."""
        if self._pipeline_builder is None:
            return
        self._running = True

    def stop(self) -> None:
        """Deterministic shutdown -- delegates the GStreamer branch
        teardown to ``VisualizationPipelineBuilder.teardown()`` (element/
        probe/pad release sequence documented there). Safe to call
        multiple times and safe to call when never initialized."""
        if self._pipeline_builder is not None and self._pipeline is not None:
            self._pipeline_builder.teardown(self._pipeline)
        self._pipeline_builder = None
        self._pipeline = None
        self._running = False

    def mark_failed(self, reason: str) -> None:
        """Called by ``builder.py``'s failure-isolation ``try/except``
        around ``initialize()``/``start()`` -- records why visualization
        didn't come up, surfaced via ``health()``, without ever raising
        back out of the caller's exception handler."""
        _logger.error("Visualization failed to start: %s", reason)
        self._pipeline_builder = None
        self._running = False
        self._reason = reason

    def health(self) -> VisualizationHealth:
        if not self._settings.enabled:
            return VisualizationHealth(
                enabled=False,
                running=False,
                bound_port=None,
                stream_name=self._settings.stream_name,
                reason=None,
            )
        return VisualizationHealth(
            enabled=True,
            running=self._running,
            bound_port=None,
            stream_name=self._settings.stream_name,
            reason=self._reason,
        )
