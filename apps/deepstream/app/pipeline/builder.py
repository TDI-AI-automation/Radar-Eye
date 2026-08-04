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
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from apps.deepstream.app.config import DeepStreamSettings, ModelsSettings, VisualizationSettings
from apps.deepstream.app.health.heartbeat import FrameCounter
from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.ingestion.source import RtspSource
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.media_publisher.tier2 import Tier2Publisher
from apps.deepstream.app.models_config import ModelConfigResolver
from apps.deepstream.app.pipeline.frame_distributor import bitstream_tee_element_name
from apps.deepstream.app.visualization.manager import VisualizationManager

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
        visualization_settings: VisualizationSettings | None = None,
        visualization_manager: VisualizationManager | None = None,
        media_publisher_enabled: bool = False,
        tier2_publisher: Tier2Publisher | None = None,
        live_stream_enabled: bool = False,
        on_source_added: Callable[[uuid.UUID, str], None] | None = None,
        on_source_removed: Callable[[uuid.UUID], None] | None = None,
        on_source_first_buffer: Callable[[uuid.UUID], None] | None = None,
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
        self._visualization_settings = visualization_settings
        self._visualization_manager = visualization_manager
        """RM-11.SIV visualization subsystem -- both optional/None-safe,
        matching heartbeat/instrumentation's pattern above. Only used when
        visualization_settings.enabled and .stream_output_enabled are both
        true (see build()); otherwise the pipeline is byte-for-byte
        identical to before this subsystem existed. initialize()/start()
        happen in add_source() rather than build() -- the visualization
        renderer needs a fixed camera_id (RM-11.SIV validates a single
        camera) that isn't known until the first camera source is added;
        build() only constructs the topology-level tee + metadata branch,
        which is camera-independent."""
        self._visualization_tee: Any = None
        self._visualization_initialized = False
        self._media_publisher_enabled = media_publisher_enabled
        self._tier2_publisher = tier2_publisher
        """RM-12 Camera Runtime Step 7 -- both optional/None-safe, same
        idiom as visualization above. Only used when
        media_publisher_enabled is true (see build()); otherwise the
        pipeline is byte-for-byte identical to before this subsystem
        existed. on_camera_added()/on_camera_removed() are called from
        add_source()/remove_source() (not build()) since Tier 2's
        per-camera branch depends on that camera's streammux pad_index,
        only known once the camera is actually added -- mirrors
        VisualizationManager's exact reasoning for the same split."""
        self._live_stream_enabled = live_stream_enabled
        self._sgie_tee: Any = None
        """Live Monitoring's WebRTC branch (apps/deepstream/app/live_stream/)
        needs a request pad off the same shared SGIE tee Visualization/
        Tier 2 already share -- see build()'s ``needs_sgie_tee``. Unlike
        those two, its own per-camera branch construction lives entirely
        outside this class (in ``live_stream/manager.py``, via the
        ``sgie_tee()`` accessor below) since it isn't scoped to a single
        camera the way Visualization is."""
        self._on_source_added = on_source_added
        self._on_source_removed = on_source_removed
        """Optional, None-safe (same idiom as visualization/tier2 above) --
        called from add_source()/remove_source() exactly where
        VisualizationManager/Tier2Publisher already are, for the same
        reason (camera_id/name/removal timing all only known here). This
        is the one hook Live Monitoring's WebRTC branch needs to build/
        tear down in lockstep with a camera's source, covering every
        removal path uniformly -- bus-message failure (_on_bus_message),
        reconnect, and deletion-driven removal (DesiredStateSynchronizer
        dropping a camera from Desired State entirely once it's deleted)
        -- without DesiredStateSynchronizer or this class needing any
        awareness of Live Monitoring itself."""
        self._on_source_first_buffer = on_source_first_buffer
        """Optional, None-safe -- fired exactly once per add_source() call
        (initial add, or a reconnect's fresh bin), the moment a real
        buffer is actually observed flowing from the camera (see
        _attach_first_buffer_probe). Observed-State-accuracy fix: unlike
        on_source_added (fired the instant the GStreamer elements are
        merely constructed and linked, before rtspsrc has necessarily
        finished its handshake with the camera), this is the earliest
        point that actually confirms the RTSP stream is delivering data
        -- runtime.py uses it, not on_source_added, to promote a camera
        to CONNECTED."""
        self._nvstreamdemux: Any = None
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
        """The streammux sink request pad ever assigned to a given camera_id
        -- kept here for its *entire process lifetime*, not just while a
        source is currently active. See remove_source()'s docstring for why
        this pad is deliberately never released."""
        self._camera_pad_index: dict[uuid.UUID, int] = {}
        """The stable pad_index (== streammux source_id) assigned to a
        camera_id the first time it is ever added -- reused, never
        reassigned, across any number of later remove/re-add cycles for the
        same camera_id. Monotonically growing (bounded by the number of
        distinct cameras ever registered during this process's life, not by
        how often any one camera is added/removed)."""
        self._pad_index_to_camera_id: dict[int, uuid.UUID] = {}
        self._ingress_timestamps: dict[int, tuple[float, datetime]] = {}
        self.pgie_is_placeholder = True
        self.sgie_is_placeholder = True
        """Set by build() from ModelConfigResolver's result -- exposed so
        callers (runtime.py, RM-11.SIV's dashboard/report) can tell real
        model results apart from placeholder-model results without
        re-reading configs/models.yaml themselves."""

    def set_tier2_publisher(self, tier2_publisher: Tier2Publisher) -> None:
        """Breaks the DeepStreamPipeline <-> MediaPublisher circular
        construction dependency: MediaPublisher needs a real pipeline
        reference at construction time (Tier1Publisher reads bin_for()
        lazily), but DeepStreamPipeline needs a Tier2Publisher reference
        before build() runs. Mirrors DeepStreamRuntime.set_health_collector()'s
        identical "setter for a not-yet-available dependency" pattern.
        Must be called before build(), the only place ``self._tier2_publisher``
        is read."""
        self._tier2_publisher = tier2_publisher

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

        visualization_active = (
            self._visualization_settings is not None
            and self._visualization_settings.enabled
            and self._visualization_settings.stream_output_enabled
        )
        needs_sgie_tee = (
            visualization_active or self._media_publisher_enabled or self._live_stream_enabled
        )

        if needs_sgie_tee:
            # A branch beyond the tail/metadata sink was requested --
            # visualization, Media Publisher Tier 2 (RM-12 Camera Runtime
            # Step 7), or both share exactly one tee immediately after
            # SGIE (an element's src pad can only feed one thing directly,
            # so both subsystems necessarily fork off the same tee when
            # both are active). Only the tee itself and this metadata-queue
            # are built here; everything downstream of any other branch is
            # that branch's own owner's exclusive responsibility
            # (VisualizationPipelineBuilder for visualization,
            # Tier2Publisher for Media Publisher -- see
            # visualization/pipeline_builder.py and
            # media_publisher/tier2.py respectively).
            #
            # buffer-pool-size: nvstreammux's own default (4) is tuned for
            # this pipeline's single original consumer -- raised for
            # additional consumers' extra headroom. Not, on its own, the
            # fix for the real corruption bug found during RM-11.SIV Phase
            # 5 hardware verification (see pipeline_builder.py's
            # disable-passthrough comment for the actual root cause and
            # fix) -- kept anyway since more than one consumer genuinely
            # needs more pool headroom than a single consumer does.
            streammux.set_property("buffer-pool-size", 16)
            tee = Gst.ElementFactory.make("tee", "sgie-tee")
            if tee is None:
                raise RuntimeError("Failed to create tee (sgie-tee)")
            self._pipeline.add(tee)
            metadata_queue = Gst.ElementFactory.make("queue", "metadata-queue")
            if metadata_queue is None:
                raise RuntimeError("Failed to create queue (metadata-queue)")
            self._pipeline.add(metadata_queue)

            sgie.link(tee)
            tee.link(metadata_queue)
            metadata_queue.link(fakesink)

            self._sgie_tee = tee
            if visualization_active:
                self._visualization_tee = tee

            if self._media_publisher_enabled:
                demux = Gst.ElementFactory.make("nvstreamdemux", "tier2-demux")
                if demux is None:
                    raise RuntimeError("Failed to create nvstreamdemux")
                self._pipeline.add(demux)
                demux_branch_pad = tee.get_request_pad("src_%u")
                if demux_branch_pad is None:
                    raise RuntimeError("Failed to request tee src pad for tier2 demux")
                demux_sink_pad = demux.get_static_pad("sink")
                if demux_branch_pad.link(demux_sink_pad) != Gst.PadLinkReturn.OK:
                    raise RuntimeError("Failed to link sgie tee to nvstreamdemux")
                self._nvstreamdemux = demux
        else:
            # Disabled (default): identical to this pipeline's behavior
            # before visualization/Media Publisher existed -- no tee, no
            # extra queue, nothing else constructed.
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

        bin_ = source.build(latency_ms=self._settings.rtsp_default_latency_ms)
        self._pipeline.add(bin_)

        # Stable pad slot: NVIDIA's own nvstreammux/nvstreamdemux plugins
        # are only ever exercised (by NVIDIA's own reference deepstream-app,
        # deepstream_source_bin.c's reset_source_pipeline()) with a
        # pre-allocated, permanently-held request pad per source -- a
        # camera being removed and later re-added reuses the exact same
        # pad_index/sink_pad rather than requesting a fresh one. See
        # remove_source()'s docstring for the full rationale (this is the
        # other half of that fix).
        if source.camera_id in self._camera_pad_index:
            pad_index = self._camera_pad_index[source.camera_id]
            sink_pad = self._request_pads[source.camera_id]
        else:
            pad_index = len(self._camera_pad_index)
            sink_pad = self._streammux.get_request_pad(f"sink_{pad_index}")
            if sink_pad is None:
                sink_pad = self._streammux.request_pad_simple(f"sink_{pad_index}")
            self._camera_pad_index[source.camera_id] = pad_index
            self._request_pads[source.camera_id] = sink_pad

        src_pad = bin_.get_static_pad("src")
        if src_pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"Failed to link source bin for camera {source.camera_id}")

        self._sources[source.camera_id] = source
        self._pad_index_to_camera_id[pad_index] = source.camera_id
        bin_.sync_state_with_parent()
        self._attach_first_buffer_probe(bin_, source.camera_id)

        # Visualization renderer needs a fixed camera_id (RM-11.SIV
        # validates a single camera), only known once a camera is actually
        # added -- see __init__'s docstring for why this can't happen in
        # build(). Guarded to run once: add_source() is also called again
        # from the reconnect path for an already-known camera, which must
        # never re-initialize (or fail trying to reuse) the branch built
        # once during the pipeline's lifetime. Failure isolation: visualization
        # must never prevent the camera source itself from being wired up.
        if (
            self._visualization_tee is not None
            and self._visualization_manager is not None
            and not self._visualization_initialized
        ):
            self._visualization_initialized = True
            try:
                self._visualization_manager.initialize(
                    self._pipeline,
                    self._visualization_tee,
                    camera_id=source.camera_id,
                    camera_name=source.camera.name,
                    instrumentation=self._instrumentation,
                )
                self._visualization_manager.start()
            except Exception as exc:  # noqa: BLE001 -- must never take inference down with it
                logger.exception(
                    "Visualization failed to start -- continuing without it "
                    "(inference is unaffected)"
                )
                self._visualization_manager.mark_failed(str(exc))

        # RM-12 Camera Runtime Step 7: Tier 2's per-camera branch depends on
        # this camera's streammux pad_index, only known now. Idempotent on
        # the reconnect path (Tier2Publisher.on_camera_added() itself
        # no-ops for an already-known camera_id). Failure isolation:
        # Media Publisher must never prevent the camera source itself from
        # being wired up, matching visualization's own guarantee above.
        if self._nvstreamdemux is not None and self._tier2_publisher is not None:
            try:
                self._tier2_publisher.on_camera_added(
                    self._pipeline,
                    self._nvstreamdemux,
                    camera_id=source.camera_id,
                    pad_index=pad_index,
                )
            except Exception:  # noqa: BLE001 -- must never take inference down with it
                logger.exception(
                    "Media Publisher Tier 2 failed to attach for camera %s -- continuing "
                    "without it (inference is unaffected)",
                    source.camera_id,
                )

        # Live Monitoring's WebRTC branch -- same failure-isolation
        # guarantee as visualization/Tier 2 above; idempotent on the
        # reconnect path (LiveStreamManager.add_camera() itself no-ops
        # for an already-known camera_id).
        if self._on_source_added is not None:
            try:
                self._on_source_added(source.camera_id, source.camera.name)
            except Exception:  # noqa: BLE001 -- must never take inference down with it
                logger.exception(
                    "Live Monitoring failed to notify of new source for camera %s -- "
                    "continuing without it (inference is unaffected)",
                    source.camera_id,
                )

    def _attach_first_buffer_probe(self, bin_: Any, camera_id: uuid.UUID) -> None:
        """One-shot: fires ``on_source_first_buffer`` the moment a real
        buffer is observed at the bitstream tee's sink pad -- fed
        directly by this camera's own ``h264parse``, before any decode/
        AI-valve dependency. Observed-State-accuracy fix: ``add_source()``
        merely constructing and linking GStreamer elements says nothing
        about whether ``rtspsrc`` has actually finished its handshake
        with the camera; this is the earliest point that confirms the
        RTSP stream is really delivering data. Removes itself after
        firing once. A no-op if no callback was supplied, or if (unit
        tests using a stub bin) the bitstream tee doesn't exist."""
        if self._on_source_first_buffer is None:
            return
        Gst = _import_gst()
        tee = bin_.get_by_name(bitstream_tee_element_name(camera_id))
        if tee is None:
            return
        pad = tee.get_static_pad("sink")
        probe_id_holder: list[int] = []

        def _on_first_buffer(_pad: Any, _info: Any) -> Any:
            if probe_id_holder:
                pad.remove_probe(probe_id_holder[0])
            callback = self._on_source_first_buffer
            if callback is not None:
                callback(camera_id)
            return Gst.PadProbeReturn.OK

        probe_id_holder.append(pad.add_probe(Gst.PadProbeType.BUFFER, _on_first_buffer))

    def is_built(self) -> bool:
        """RM-12 Camera Runtime Step 5 (Telemetry): a passive readiness
        check -- true once ``build()`` has constructed the shared
        streammux/PGIE/tracker/SGIE topology. Does not distinguish "elements
        constructed" from "TensorRT engines fully warmed" (``build()``
        itself doesn't observably separate those two moments); Telemetry
        reads this, nothing about pipeline construction changes because of
        it."""
        return self._streammux is not None

    def active_camera_ids(self) -> frozenset[uuid.UUID]:
        """Every camera_id with a currently active source. RM-12 Camera
        Runtime Step 4: ``DesiredStateSynchronizer`` uses this to find
        sources that must be removed because their camera no longer
        appears in Camera Registry's Desired State at all (deleted)."""
        return frozenset(self._sources.keys())

    def gst_pipeline(self) -> Any:
        """The real ``Gst.Pipeline`` -- for callers (Live Monitoring's
        WebRTC branch) that need to ``add()``/``remove()`` elements
        directly, which this wrapper class itself doesn't expose."""
        return self._pipeline

    def sgie_tee(self) -> Any | None:
        """The shared tee immediately after SGIE, or ``None`` if nothing
        requested one (``needs_sgie_tee`` was false at ``build()`` time).
        Visualization/Tier 2/Live Monitoring's WebRTC branch each request
        their own ``src_%u`` pad off this same element -- an element's
        output can only feed one thing directly, so a tee is exactly the
        "more than one subsystem forks off SGIE" primitive; this accessor
        is the one place any of them reach it."""
        return self._sgie_tee

    def camera_name_for(self, camera_id: uuid.UUID) -> str | None:
        """The camera's registered name, or ``None`` if no source is
        currently active for it -- for callers (Live Monitoring's WebRTC
        branch) that need it at a point where they only have the
        camera_id, mirroring ``bin_for()``'s exact shape."""
        source = self._sources.get(camera_id)
        return source.camera.name if source is not None else None

    def bin_for(self, camera_id: uuid.UUID) -> Any | None:
        """The camera's ``Gst.Bin``, or ``None`` if no source is currently
        active for it. RM-12 Camera Runtime Step 3: Runtime Supervisor's
        sole read access into pipeline internals -- it locates the valve via
        ``bin_.get_by_name(valve_element_name(camera_id))`` (see
        ``ingestion/source.py``'s ``valve_element_name`` docstring), never
        reaching into ``DeepStreamPipeline``'s other private state."""
        source = self._sources.get(camera_id)
        return source.bin if source is not None else None

    def remove_source(self, camera_id: uuid.UUID) -> None:
        """Tears down this camera's decoder bin. Does **not** release its
        streammux sink request pad -- see the comment at the end of this
        method's body for the full, hardware-confirmed rationale. ``_request_pads``
        and ``_camera_pad_index`` are deliberately left untouched (they
        persist for the process's life); only ``_sources`` and
        ``_pad_index_to_camera_id`` -- which track *currently active*
        cameras -- are cleared here.
        """
        source = self._sources.pop(camera_id, None)
        sink_pad = self._request_pads.get(camera_id)
        self._pad_index_to_camera_id = {
            index: cid for index, cid in self._pad_index_to_camera_id.items() if cid != camera_id
        }
        if source is None or source.bin is None:
            return

        Gst = _import_gst()
        ghost_src_pad = source.bin.get_static_pad("src")

        # Officially-supported NVIDIA synchronization primitive (not a
        # hand-rolled substitute): GST_NVEVENT_STREAM_RESET is the
        # nvstreammux-specific, per-source-id, DOWNSTREAM|SERIALIZED|STICKY
        # custom event (gst-nvevent.h, shipped with the DeepStream SDK)
        # NVIDIA's own reference deepstream-app sends before tearing down a
        # source's state (apps-common/src/deepstream_source_bin.c,
        # reset_source_pipeline()) -- exposed to Python via
        # pyds.gst_element_send_nvevent_new_stream_reset(), whose own
        # docstring says it exists to "reset the source in case RTSP
        # reconnection is required". Being SERIALIZED, it queues in-band
        # with this source's already-batched buffers rather than jumping
        # the queue, letting nvstreammux settle this source_id's internal
        # state at the correct point in the data flow before its pad goes
        # quiet. Sent on the streammux element itself (the "element to
        # which the generated event needs to be sent", per the function's
        # own docstring), addressed by this camera's stable pad_index.
        pad_index = self._camera_pad_index.get(camera_id)
        if pad_index is not None:
            try:
                import pyds  # noqa: PLC0415 -- deferred, DeepStream SDK-provided

                pyds.gst_element_send_nvevent_new_stream_reset(hash(self._streammux), pad_index)
            except Exception:  # noqa: BLE001 -- best-effort notification, never fatal
                logger.exception(
                    "Failed to send stream-reset nvevent for camera %s -- continuing anyway",
                    camera_id,
                )

        # Defense in depth alongside the nvevent above: block this bin's
        # own ghost "src" pad with an IDLE probe before destroying the
        # decoder. An IDLE probe's callback only fires once the pad has no
        # buffer currently mid-push through it -- since this bin has no
        # queue between the decoder and the ghost pad on the AI path (see
        # ingestion/source.py's docstring), that guarantees streammux's
        # chain() function for this source's sink pad has already returned
        # by the time the probe fires, and the block guarantees no further
        # buffer follows. The callback fires on whichever thread is
        # currently pushing through this pad (the decoder's own internal
        # streaming thread, never the GLib main-loop thread this method
        # runs on), so waiting here cannot deadlock against it. Bounded
        # with a timeout, matching this module's own "log and proceed"
        # failure-isolation convention (e.g. AsyncBridge.stop()).
        quiesced = threading.Event()

        def _on_idle(_pad: Any, _info: Any) -> Any:
            quiesced.set()
            return Gst.PadProbeReturn.OK

        probe_id = ghost_src_pad.add_probe(Gst.PadProbeType.IDLE, _on_idle)
        if not quiesced.wait(timeout=1.0):
            logger.warning(
                "Timed out quiescing camera %s's source before teardown -- proceeding anyway",
                camera_id,
            )
        ghost_src_pad.remove_probe(probe_id)

        # RM-12 Camera Runtime Step 7: Tier 2's branch lives off the shared
        # nvstreamdemux, entirely separate from the source bin torn down
        # below -- failure isolation matches add_source()'s guarantee. Its
        # own request pad on nvstreamdemux is, by the same rationale as
        # streammux's below, never released either (see tier2.py).
        # Live Monitoring's WebRTC branch -- called before the source bin
        # itself is torn down below, same as Tier 2 above. The actual
        # teardown this triggers is scheduled (async), not synchronous
        # here -- Tier1Publisher's own detach() already tolerates the pad
        # being gone by the time it runs (see media_publisher/base.py's
        # _do_detach docstring), so ordering relative to the source bin's
        # own synchronous teardown below is not required to be exact.
        if self._on_source_removed is not None:
            try:
                self._on_source_removed(camera_id)
            except Exception:  # noqa: BLE001 -- must never prevent source teardown
                logger.exception(
                    "Live Monitoring failed to notify of source removal for camera %s",
                    camera_id,
                )

        if self._tier2_publisher is not None:
            try:
                self._tier2_publisher.on_camera_removed(camera_id)
            except Exception:  # noqa: BLE001 -- must never prevent source teardown
                logger.exception(
                    "Media Publisher Tier 2 failed to detach for camera %s -- continuing "
                    "with source teardown",
                    camera_id,
                )

        if sink_pad is not None and ghost_src_pad.is_linked():
            ghost_src_pad.unlink(sink_pad)
        source.bin.set_state(Gst.State.NULL)
        self._pipeline.remove(source.bin)
        # sink_pad is deliberately NOT released here:
        #
        # Root cause (confirmed on real hardware): the original
        # implementation called self._streammux.release_request_pad(sink_pad)
        # immediately after tearing down the source. This reproduced a real
        # segfault in libgstnvvideoconvert.so (on the visualization branch's
        # viz-queue streaming thread) every time a camera was removed while
        # Visualization + Media Publisher (Tier 2/nvstreamdemux) were both
        # active. Blocking the decoder-side race alone (the IDLE probe
        # above) did NOT stop the crash on its own -- it reproduced
        # identically with that guard already in place, proving the pad
        # *release* itself, not just decoder teardown timing, is what
        # nvstreammux/nvstreamdemux cannot tolerate while the pipeline is
        # live. This matches NVIDIA's own reference implementation
        # (deepstream-app's apps-common/src/deepstream_source_bin.c) and
        # multiple independent NVIDIA Developer Forum threads on dynamic
        # source add/remove: request pads on nvstreammux/nvstreamdemux are
        # meant to be requested once and never released while sources are
        # added and removed at runtime -- only linked and unlinked. This
        # codebase adopts that exact pattern: __init__'s
        # ``_camera_pad_index``/``_request_pads`` assign each camera_id a
        # pad_index/sink_pad exactly once, kept for the rest of the
        # process's life; remove_source() only unlinks; add_source() reuses
        # the same slot on any later re-add for that same camera_id.
        # Tier2Publisher.on_camera_removed() (tier2.py) follows the
        # identical pattern for nvstreamdemux's per-camera request pad, for
        # the same documented reason.

    def start(self) -> None:
        Gst = _import_gst()
        self._pipeline.set_state(Gst.State.PLAYING)

    def stop(self) -> None:
        if self._visualization_manager is not None:
            self._visualization_manager.stop()
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
