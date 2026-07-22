"""Shared GStreamer pipeline: nvstreammux + per-camera source bins.

Source: DEEPSTREAM_PIPELINE_SPEC.md Stage 2 (StreamMux). Phase 0 scope only
(per the RM-11 design review's approved implementation order) -- no PGIE,
tracker, or SGIE yet. After streammux, frames are counted (for heartbeat
FPS, see health/heartbeat.py) and dropped via fakesink. PGIE/tracker/SGIE
attach after streammux in Phase 1/2, replacing the fakesink tail.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from apps.deepstream.app.config import DeepStreamSettings
from apps.deepstream.app.health.heartbeat import FrameCounter
from apps.deepstream.app.ingestion.source import RtspSource

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    Gst.init(None)
    return Gst


BusMessageHandler = Callable[[Any], None]


class DeepStreamPipeline:
    """Owns the ``Gst.Pipeline``, the shared ``nvstreammux``, and the set of
    active per-camera source bins."""

    def __init__(
        self,
        settings: DeepStreamSettings,
        *,
        frame_counter: FrameCounter,
        on_bus_message: BusMessageHandler | None = None,
    ) -> None:
        self._settings = settings
        self._frame_counter = frame_counter
        self._on_bus_message = on_bus_message
        self._pipeline: Any = None
        self._streammux: Any = None
        self._sources: dict[uuid.UUID, RtspSource] = {}
        self._request_pads: dict[uuid.UUID, Any] = {}

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
        self._pipeline.add(streammux)
        self._streammux = streammux

        # Phase 0 tail: count frames post-batch, then drop. PGIE/tracker/SGIE
        # (Phase 1/2) replace everything between streammux and fakesink.
        fakesink = Gst.ElementFactory.make("fakesink", "phase0-sink")
        fakesink.set_property("sync", 0)
        self._pipeline.add(fakesink)
        streammux.link(fakesink)

        sink_pad = fakesink.get_static_pad("sink")
        sink_pad.add_probe(Gst.PadProbeType.BUFFER, self._count_frame_probe)

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._handle_bus_message)

    def _count_frame_probe(self, _pad: Any, _info: Any) -> Any:
        Gst = _import_gst()
        # Phase 0 has no per-source batch-id demux yet -- single aggregate
        # counter until NvDsBatchMeta parsing arrives with PGIE (Phase 1).
        for camera_id in self._sources:
            self._frame_counter.increment(camera_id)
            break
        return Gst.PadProbeReturn.OK

    def add_source(self, source: RtspSource) -> None:
        Gst = _import_gst()
        if self._pipeline is None or self._streammux is None:
            raise RuntimeError("build() must be called before add_source()")

        bin_ = source.build()
        self._pipeline.add(bin_)

        sink_pad = self._streammux.get_request_pad(f"sink_{len(self._request_pads)}")
        if sink_pad is None:
            sink_pad = self._streammux.request_pad_simple(f"sink_{len(self._request_pads)}")
        src_pad = bin_.get_static_pad("src")
        if src_pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"Failed to link source bin for camera {source.camera_id}")

        self._sources[source.camera_id] = source
        self._request_pads[source.camera_id] = sink_pad
        bin_.sync_state_with_parent()

    def remove_source(self, camera_id: uuid.UUID) -> None:
        source = self._sources.pop(camera_id, None)
        sink_pad = self._request_pads.pop(camera_id, None)
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

    def _handle_bus_message(self, _bus: Any, message: Any) -> None:
        if self._on_bus_message is not None:
            self._on_bus_message(message)

    def source_for_message(self, message: Any) -> RtspSource | None:
        for source in self._sources.values():
            if source.is_failure_message(message):
                return source
        return None
