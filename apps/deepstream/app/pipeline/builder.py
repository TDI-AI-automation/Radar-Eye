"""Shared GStreamer pipeline: nvstreammux + per-camera source bins + PGIE/tracker/SGIE.

Source: DEEPSTREAM_PIPELINE_SPEC.md Stage 2 (StreamMux), Stage 3 (Primary
GIE), Stage 4 (Tracking), Stage 5 (Secondary GIE). Phase 1 (PGIE, placeholder
model, see apps/deepstream/configs/pgie_placeholder.txt; NvDCF tracker) and
Phase 2 (SGIE, placeholder classifier, see
apps/deepstream/configs/sgie_placeholder.txt) both attach between streammux
and the tail sink, per each phase's approval.

Per ADR-027, this module builds and wires GStreamer/DeepStream *elements*
only -- it never touches ``pyds`` or parses ``NvDsBatchMeta`` itself. The
inference pad probe extracts nothing on its own; it hands the raw
``Gst.Buffer`` straight to the injected ``on_inference_buffer`` callback
(owned by ``runtime.py``, which routes it into ``RuntimeAdapter`` -- the
only module permitted to parse it).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from apps.deepstream.app.config import DeepStreamSettings, ModelsSettings
from apps.deepstream.app.health.heartbeat import FrameCounter
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.models_config import ModelConfigResolver

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    Gst.init(None)
    return Gst


BusMessageHandler = Callable[[Any], None]
InferenceBufferHandler = Callable[[Any, dict[int, uuid.UUID], float, datetime], None]
"""(gst_buffer, pad_index -> camera_id, ingress_monotonic_seconds, ingress_wallclock).

Two clocks, deliberately: the monotonic value is for latency *measurement*
(immune to wall-clock adjustments), the wall-clock value is for
FrameObservation's timestamp fields (semantically real dates). Never
convert one into the other -- see observations.build_frame_observation's
docstring."""

_INGRESS_TIMESTAMP_CAP = 256
"""Bound on the ingress-timestamp correlation dict -- protects against
unbounded growth if a buffer never reaches the inference probe (e.g. a
pipeline error mid-batch); frames this old are stale well before it fills."""


class DeepStreamPipeline:
    """Owns the ``Gst.Pipeline``, the shared ``nvstreammux``/PGIE/tracker,
    and the set of active per-camera source bins."""

    def __init__(
        self,
        settings: DeepStreamSettings,
        models: ModelsSettings,
        *,
        frame_counter: FrameCounter,
        on_bus_message: BusMessageHandler | None = None,
        on_inference_buffer: InferenceBufferHandler | None = None,
        model_config_resolver: ModelConfigResolver | None = None,
        heartbeat: HeartbeatRegistry | None = None,
        instrumentation: PerformanceInstrumentation | None = None,
    ) -> None:
        self._settings = settings
        self._models = models
        self._instrumentation = instrumentation
        """RM-11.SIV Task 7 -- optional, feeds record_pgie_frame()/
        record_sgie_frame() from the alive probes below."""
        self._model_config_resolver = model_config_resolver or ModelConfigResolver()
        self._heartbeat = heartbeat
        """RM-11.SIV Unified Heartbeat -- optional, see threat_runtime_adapter.py's
        identical pattern. Fed by pad probes below (pgie/tracker/sgie
        element-level liveness) and _count_frame_probe (rtsp)."""
        self._frame_counter = frame_counter
        self._on_bus_message = on_bus_message
        self._on_inference_buffer = on_inference_buffer
        self._pipeline: Any = None
        self._streammux: Any = None
        self._pgie: Any = None
        self._tracker: Any = None
        self._sgie: Any = None
        self._sources: dict[uuid.UUID, RtspSource] = {}
        self._request_pads: dict[uuid.UUID, Any] = {}
        self._pad_index_to_camera_id: dict[int, uuid.UUID] = {}
        self._ingress_timestamps: dict[int, tuple[float, datetime]] = {}
        self.pgie_is_placeholder = True
        self.sgie_is_placeholder = True
        """Set by build() from ModelConfigResolver's result -- exposed so
        callers (runtime.py, RM-11.SIV's dashboard/report) can tell real
        model results apart from placeholder-model results without
        re-reading configs/models.yaml themselves."""

    def build(self) -> None:
        Gst = _import_gst()

        self._pipeline = Gst.Pipeline.new("radar-eye-deepstream")

        streammux = Gst.ElementFactory.make("nvstreammux", "streammux")
        if streammux is None:
            raise RuntimeError("Failed to create nvstreammux")
        streammux.set_property("batch-size", self._settings.streammux_batch_size)
        streammux.set_property("width", self._settings.streammux_width)
        streammux.set_property("height", self._settings.streammux_height)
        streammux.set_property("live-source", 1)
        streammux.set_property(
            "batched-push-timeout", self._settings.streammux_batched_push_timeout_us
        )
        self._pipeline.add(streammux)
        self._streammux = streammux

        pgie = Gst.ElementFactory.make("nvinfer", "pgie")
        if pgie is None:
            raise RuntimeError("Failed to create nvinfer (PGIE)")
        resolved_pgie = self._model_config_resolver.resolve_pgie(self._models)
        self.pgie_is_placeholder = resolved_pgie.is_placeholder
        pgie_config_path = self._resolve_config_path(str(resolved_pgie.config_file_path))
        pgie.set_property("config-file-path", str(pgie_config_path))
        self._pipeline.add(pgie)
        self._pgie = pgie

        tracker = Gst.ElementFactory.make("nvtracker", "tracker")
        if tracker is None:
            raise RuntimeError("Failed to create nvtracker (NvDCF)")
        tracker.set_property("tracker-width", self._settings.tracker_width)
        tracker.set_property("tracker-height", self._settings.tracker_height)
        tracker.set_property("ll-lib-file", self._settings.tracker_ll_lib_path)
        tracker.set_property("ll-config-file", self._settings.tracker_ll_config_path)
        self._pipeline.add(tracker)
        self._tracker = tracker

        sgie = Gst.ElementFactory.make("nvinfer", "sgie")
        if sgie is None:
            raise RuntimeError("Failed to create nvinfer (SGIE)")
        resolved_sgie = self._model_config_resolver.resolve_sgie(self._models)
        self.sgie_is_placeholder = resolved_sgie.is_placeholder
        sgie_config_path = self._resolve_config_path(str(resolved_sgie.config_file_path))
        sgie.set_property("config-file-path", str(sgie_config_path))
        self._pipeline.add(sgie)
        self._sgie = sgie

        fakesink = Gst.ElementFactory.make("fakesink", "tail-sink")
        fakesink.set_property("sync", 0)
        self._pipeline.add(fakesink)

        streammux.link(pgie)
        pgie.link(tracker)
        tracker.link(sgie)
        sgie.link(fakesink)

        # Heartbeat FPS counting (Phase 0, RM-09 integration) -- unchanged,
        # still counts every batched frame regardless of inference result.
        streammux_src_pad = streammux.get_static_pad("src")
        streammux_src_pad.add_probe(Gst.PadProbeType.BUFFER, self._count_frame_probe)

        # RM-11.SIV: element-level liveness only ("a buffer passed through
        # this element just now") -- cheap, content-free, feeds the
        # watchdog's per-stage staleness check. Deliberately not merged with
        # the SGIE probe below: PGIE/tracker can be silently starved (e.g. a
        # bad tracker config) while the pipeline still nominally runs.
        pgie_src_pad = pgie.get_static_pad("src")
        pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, self._pgie_alive_probe)
        tracker_src_pad = tracker.get_static_pad("src")
        tracker_src_pad.add_probe(Gst.PadProbeType.BUFFER, self._tracker_alive_probe)

        # Phase 2: post-classification metadata (detections carry both
        # track IDs and, where applicable, SGIE classifier output by this
        # point). Extraction itself happens in RuntimeAdapter, not here --
        # see the module docstring and ADR-027.
        sgie_src_pad = sgie.get_static_pad("src")
        sgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, self._inference_buffer_probe)

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._handle_bus_message)

    @staticmethod
    def _resolve_config_path(path: str) -> Any:
        from pathlib import (
            Path,  # noqa: PLC0415 -- avoids a module-level dependency on config.py's REPO_ROOT
        )

        from apps.deepstream.app.config import REPO_ROOT

        candidate = Path(path)
        return candidate if candidate.is_absolute() else REPO_ROOT / candidate

    def _beat(self, component: str) -> None:
        if self._heartbeat is not None:
            self._heartbeat.beat(component)

    def _pgie_alive_probe(self, _pad: Any, _info: Any) -> Any:
        self._beat("pgie")
        if self._instrumentation is not None:
            self._instrumentation.record_pgie_frame()
        return _import_gst().PadProbeReturn.OK

    def _tracker_alive_probe(self, _pad: Any, _info: Any) -> Any:
        self._beat("tracker")
        return _import_gst().PadProbeReturn.OK

    def _count_frame_probe(self, _pad: Any, info: Any) -> Any:
        Gst = _import_gst()
        self._beat("rtsp")
        for camera_id in self._sources:
            self._frame_counter.increment(camera_id)
            break

        # Ingress-timestamp side of the RM-11 Phase 1 latency instrumentation
        # requirement ("frame ingress -> metadata available"): recorded here,
        # at streammux's output, and consumed in _inference_buffer_probe
        # further downstream, correlated by buffer identity. In-place
        # DeepStream metadata attachment means the same Gst.Buffer object
        # flows through PGIE/tracker, so hash(gst_buffer) is a valid key.
        gst_buffer = info.get_buffer()
        if gst_buffer is not None:
            if len(self._ingress_timestamps) >= _INGRESS_TIMESTAMP_CAP:
                self._ingress_timestamps.pop(next(iter(self._ingress_timestamps)))
            self._ingress_timestamps[hash(gst_buffer)] = (
                time.monotonic(),
                datetime.now(timezone.utc),
            )

        return Gst.PadProbeReturn.OK

    def _inference_buffer_probe(self, _pad: Any, info: Any) -> Any:
        Gst = _import_gst()
        self._beat("sgie")
        if self._instrumentation is not None:
            self._instrumentation.record_sgie_frame()
        if self._on_inference_buffer is not None:
            gst_buffer = info.get_buffer()
            if gst_buffer is not None:
                ingress_monotonic, ingress_wallclock = self._ingress_timestamps.pop(
                    hash(gst_buffer), (time.monotonic(), datetime.now(timezone.utc))
                )
                self._on_inference_buffer(
                    gst_buffer,
                    dict(self._pad_index_to_camera_id),
                    ingress_monotonic,
                    ingress_wallclock,
                )
        return Gst.PadProbeReturn.OK

    def add_source(self, source: RtspSource) -> None:
        Gst = _import_gst()
        if self._pipeline is None or self._streammux is None:
            raise RuntimeError("build() must be called before add_source()")

        pad_index = len(self._request_pads)
        bin_ = source.build(latency_ms=self._settings.rtsp_default_latency_ms)
        self._pipeline.add(bin_)

        sink_pad = self._streammux.get_request_pad(f"sink_{pad_index}")
        if sink_pad is None:
            sink_pad = self._streammux.request_pad_simple(f"sink_{pad_index}")
        src_pad = bin_.get_static_pad("src")
        if src_pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"Failed to link source bin for camera {source.camera_id}")

        self._sources[source.camera_id] = source
        self._request_pads[source.camera_id] = sink_pad
        self._pad_index_to_camera_id[pad_index] = source.camera_id
        bin_.sync_state_with_parent()

    def remove_source(self, camera_id: uuid.UUID) -> None:
        source = self._sources.pop(camera_id, None)
        sink_pad = self._request_pads.pop(camera_id, None)
        self._pad_index_to_camera_id = {
            index: cid for index, cid in self._pad_index_to_camera_id.items() if cid != camera_id
        }
        if source is None or source.bin is None:
            return
        source.bin.set_state(_import_gst().State.NULL)
        if sink_pad is not None:
            self._streammux.release_request_pad(sink_pad)
        self._pipeline.remove(source.bin)

    def start(self) -> None:
        Gst = _import_gst()
        self._pipeline.set_state(Gst.State.PLAYING)

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(_import_gst().State.NULL)

    def is_pipeline_state_changed_to_playing(self, message: Any) -> bool:
        """True if ``message`` reports this (top-level) pipeline reaching
        PLAYING -- used for the RM-11 Phase 1 pipeline-startup-time metric.
        Deliberately narrow (only PLAYING, only the top-level pipeline) --
        callers don't need this element's identity beyond that."""
        Gst = _import_gst()
        if message.type != Gst.MessageType.STATE_CHANGED or message.src != self._pipeline:
            return False
        _old, new_state, _pending = message.parse_state_changed()
        return bool(new_state == Gst.State.PLAYING)

    def _handle_bus_message(self, _bus: Any, message: Any) -> None:
        if self._on_bus_message is not None:
            self._on_bus_message(message)

    def source_for_message(self, message: Any) -> RtspSource | None:
        for source in self._sources.values():
            if source.is_failure_message(message):
                return source
        return None
