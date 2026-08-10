"""DeepStreamOverlayRenderer -- the only ``pyds``-touching code in the
visualization subsystem, RM-11.SIV.

Mirrors ``apps/deepstream/app/runtime_adapter.py``'s role as the sole
``pyds``-importing module for its own concern: this file's only job is to
read already-computed ``obj_meta``/``frame_meta`` fields and the
``TrackAnnotationRegistry``, then write DeepStream's own display-metadata
fields. No color decision, no formatting, no text composition lives here --
every such decision is a call into ``overlay.py`` (pure Python, no ``pyds``
dependency, unit-tested there instead of here).

Metadata immutability (hard constraint): this class may write *only*
``rect_params``/``text_params`` on existing ``obj_meta`` objects and add new
``NvDsDisplayMeta`` objects -- the fields DeepStream defines specifically
for on-screen display. It must never write ``class_id``, ``obj_label``,
``confidence``, ``object_id`` (tracking id), or any other detection/
classification field, and never touches anything ``RuntimeAdapter`` or
``ThreatEngineRuntimeAdapter`` reads -- this branch is strictly read-only
with respect to inference metadata, consuming it, never mutating it.

Not unit-tested here (same established convention as
``RuntimeAdapter.extract_frame_observations``: ``pyds``-dependent code is
verified on real hardware, not mocked in pytest) -- see
docs/SIV_BASELINE.md for hardware verification results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from apps.deepstream.app.config import VisualizationSettings
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.stage_logging import get_stage_logger
from apps.deepstream.app.visualization import overlay
from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

_logger = get_stage_logger("visualization")


class DeepStreamOverlayRenderer:
    """One instance per pipeline. ``probe_callback`` is the actual
    ``add_probe`` target; ``camera_id`` is fixed at construction since
    RM-11.SIV validates a single camera (multi-camera track-annotation
    lookups already key by ``camera_id``, ready for RM-11 Phase 3)."""

    def __init__(
        self,
        settings: VisualizationSettings,
        *,
        camera_id: uuid.UUID,
        camera_name: str,
        track_annotations: TrackAnnotationRegistry,
        instrumentation: PerformanceInstrumentation | None = None,
    ) -> None:
        self._settings = settings
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._track_annotations = track_annotations
        self._instrumentation = instrumentation

    def probe_callback(self, _pad: Any, info: Any) -> Any:
        import time  # noqa: PLC0415 -- overlay-timing measurement, local to this callback

        Gst = _import_gst()
        gst_buffer = info.get_buffer()
        if gst_buffer is None:
            return Gst.PadProbeReturn.OK

        start = time.monotonic()
        try:
            self._render(gst_buffer)
        except Exception:
            # A rendering bug must never take the pipeline down with it --
            # the annotate probe runs on the visualization branch only
            # (never on the inference branch's own probes), but a raised
            # exception from a pad probe callback still propagates into
            # GStreamer's C call stack. Log and drop this frame's overlay
            # rather than risk that.
            _logger.exception("Overlay rendering failed for one frame -- skipped")
            return Gst.PadProbeReturn.OK

        elapsed_ms = (time.monotonic() - start) * 1000.0
        if self._instrumentation is not None:
            self._instrumentation.record_visualization_frame(overlay_time_ms=elapsed_ms)
        return Gst.PadProbeReturn.OK

    def _render(self, gst_buffer: Any) -> None:
        import pyds  # noqa: PLC0415 -- deferred: provided by the DeepStream SDK, not pip

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        if batch_meta is None:
            return

        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            self._render_objects(frame_meta)
            self._render_frame_overlay(batch_meta, frame_meta)
            l_frame = l_frame.next

    def _render_objects(self, frame_meta: Any) -> None:
        import pyds  # noqa: PLC0415

        # Not present in every pyds build (confirmed absent on this
        # machine's pyds 1.1.11) -- same getattr-with-None-fallback pattern
        # RuntimeAdapter._extract_raw_detections already uses for the exact
        # same constant.
        untracked_id = getattr(pyds, "UNTRACKED_OBJECT_ID", None)

        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            track_id = obj_meta.object_id if obj_meta.object_id != untracked_id else None
            annotation = (
                self._track_annotations.get(self._camera_id, track_id)
                if track_id is not None
                else None
            )

            color = overlay.resolve_color(
                class_label=obj_meta.obj_label,
                threat_level=annotation.threat_level if annotation is not None else None,
                color_scheme=self._settings.color_scheme,
                draw_threat=self._settings.draw_threat,
            )
            obj_meta.rect_params.border_color.set(*color)
            obj_meta.rect_params.border_width = self._settings.line_thickness

            text = overlay.compose_object_text(
                class_label=obj_meta.obj_label,
                confidence=obj_meta.confidence,
                track_id=track_id,
                secondary_label=_secondary_label(obj_meta),
                zone=annotation.zone if annotation is not None else None,
                distance_meters=annotation.distance_meters if annotation is not None else None,
                threat_level=annotation.threat_level if annotation is not None else None,
                settings=self._settings,
            )
            obj_meta.text_params.display_text = text
            obj_meta.text_params.font_params.font_size = self._settings.font_size
            obj_meta.text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
            obj_meta.text_params.set_bg_clr = 1
            obj_meta.text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)

            l_obj = l_obj.next

    def _render_frame_overlay(self, batch_meta: Any, frame_meta: Any) -> None:
        import pyds  # noqa: PLC0415

        snapshot = self._instrumentation.snapshot() if self._instrumentation is not None else None
        text = overlay.compose_frame_text(
            camera_name=self._camera_name,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            fps=snapshot.pgie_fps if snapshot is not None else None,
            latency_ms=snapshot.end_to_end_latency_ms if snapshot is not None else None,
            gpu_percent=snapshot.gpu_utilization_pct if snapshot is not None else None,
            system_status=None,
            settings=self._settings,
        )
        if not text:
            return

        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        text_params = display_meta.text_params[0]
        text_params.display_text = text
        text_params.x_offset = 10
        text_params.y_offset = 10
        text_params.font_params.font_name = "Serif"
        text_params.font_params.font_size = self._settings.font_size
        text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
        text_params.set_bg_clr = 1
        text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


def _secondary_label(obj_meta: Any) -> str | None:
    """First classifier result's first label, if SGIE has classified this
    object -- mirrors ``RuntimeAdapter._extract_secondary_label``'s exact
    logic (duplicated rather than imported: that method is private to
    ``RuntimeAdapter``, and this is a read of the same public ``pyds``
    metadata shape, not a second extraction path for anything
    ``RuntimeAdapter`` itself produces)."""
    import pyds  # noqa: PLC0415

    l_classifier = obj_meta.classifier_meta_list
    if l_classifier is None:
        return None
    classifier_meta = pyds.NvDsClassifierMeta.cast(l_classifier.data)
    l_label = classifier_meta.label_info_list
    if l_label is None:
        return None
    label_info = pyds.NvDsLabelInfo.cast(l_label.data)
    return str(label_info.result_label) if label_info.result_label else None


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst
