"""RTSP implementation of the Media Distribution Interface -- the Phase 1
transport (ADR-028), not the architectural contract itself (see
``interface.py``).

Publish side reuses the exact "encode -> rtph264pay -> udpsink (local
loopback) -> GstRtspServer wraps a udpsrc reading that port" pattern
already hardware-verified in
``apps/deepstream/app/visualization/stream_server.py`` (RM-11.SIV) --
proven on this exact hardware, including the ``name=pay0`` requirement
GstRtspServer's SDP generation needs. One ``GstRtspServer.RTSPServer``
per publishing process, one mount point + one local UDP relay port per
published camera.

Subscribe side (``build_rtsp_source_element``) mirrors
``apps/deepstream/app/ingestion/source.py``'s proven
``rtspsrc``-with-dynamic-pad-link shape, minus everything specific to
that module (no decode, no bitstream tee, no valve -- just
``rtspsrc -> depay -> h264parse -> [ghost pad]``), since every consumer
of a republished endpoint needs the same minimal chain regardless of
which subsystem published it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from shared.media_transport.interface import MediaEndpoint

logger = logging.getLogger(__name__)


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


def _import_gst_rtsp_server() -> Any:
    import gi  # noqa: PLC0415

    gi.require_version("GstRtspServer", "1.0")
    from gi.repository import GstRtspServer  # noqa: PLC0415

    return GstRtspServer


def _import_glib() -> Any:
    import gi  # noqa: PLC0415

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib  # noqa: PLC0415

    return GLib


class RtspMediaPublisher:
    """Implements ``MediaPublisher``. One instance per publishing
    process -- owns one shared ``RTSPServer`` with one mount point per
    published camera. GLib main-loop thread only (construction, publish,
    unpublish all mutate the pipeline/server, matching this codebase's
    "every pipeline mutation happens on the GLib thread" discipline)."""

    def __init__(
        self,
        pipeline: Any,
        *,
        host: str,
        rtsp_port: int,
        udp_port_range_start: int,
        subsystem: str,
    ) -> None:
        self._pipeline = pipeline
        self._host = host
        self._rtsp_port = rtsp_port
        self._next_udp_port = udp_port_range_start
        self._subsystem = subsystem
        self._server: Any = None
        self._server_source_id: int | None = None
        self._published: dict[uuid.UUID, dict[str, Any]] = {}
        """camera_id -> {"payloader": ..., "sink": ..., "udp_port": int}
        -- enough to tear down publish() on unpublish()."""

    def start(self) -> None:
        """Binds the RTSP server. Call once, before any publish()."""
        GstRtspServer = _import_gst_rtsp_server()
        server = GstRtspServer.RTSPServer()
        server.set_service(str(self._rtsp_port))
        source_id = server.attach(None)
        if source_id == 0:
            raise RuntimeError(
                f"Failed to attach RTSP server on port {self._rtsp_port} "
                "(already in use by another process?)"
            )
        self._server = server
        self._server_source_id = source_id

    def publish(self, camera_id: uuid.UUID, source_pad: Any) -> MediaEndpoint:
        """Idempotent -- an already-published camera_id returns its
        existing endpoint unchanged."""
        if camera_id in self._published:
            return self._endpoint_for(camera_id)
        if self._server is None:
            raise RuntimeError("RtspMediaPublisher.start() has not been called")
        Gst = _import_gst()
        GstRtspServer = _import_gst_rtsp_server()

        udp_port = self._next_udp_port
        self._next_udp_port += 1

        # h264parse's output stream-format is negotiated, not fixed --
        # left unconstrained it defaults to "avc" (length-prefixed NALs,
        # out-of-band codec_data), hardware-confirmed via a real
        # pipeline run. rtph264pay needs "byte-stream" (in-band NAL
        # start codes) to correctly locate and, with config-interval=-1
        # below, periodically re-insert SPS/PPS -- with avc input it
        # silently produces an RTP stream the payload type/SDP looks
        # correct for but that never actually decodes on the subscriber
        # side. This capsfilter is the fix: it's what makes h264parse
        # (wherever it lives upstream of this publisher -- this
        # publisher never constructs its own) renegotiate to
        # byte-stream, the same way any downstream caps constraint
        # normally steers an upstream parser's output format.
        caps_filter = Gst.ElementFactory.make("capsfilter", f"media-caps-{camera_id}")
        if caps_filter is None:
            raise RuntimeError("Failed to create capsfilter")
        caps_filter.set_property(
            "caps", Gst.Caps.from_string("video/x-h264,stream-format=byte-stream,alignment=au")
        )

        payloader = Gst.ElementFactory.make("rtph264pay", f"media-pay-{camera_id}")
        if payloader is None:
            raise RuntimeError("Failed to create rtph264pay")
        payloader.set_property("pt", 96)
        payloader.set_property("config-interval", -1)  # in-band SPS/PPS every keyframe

        sink = Gst.ElementFactory.make("udpsink", f"media-udpsink-{camera_id}")
        if sink is None:
            raise RuntimeError("Failed to create udpsink")
        sink.set_property("host", "127.0.0.1")
        sink.set_property("port", udp_port)
        sink.set_property("sync", False)
        sink.set_property("async", False)

        self._pipeline.add(caps_filter)
        self._pipeline.add(payloader)
        self._pipeline.add(sink)
        if source_pad.link(caps_filter.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            raise RuntimeError(f"Failed to link source pad to capsfilter for camera {camera_id}")
        if not caps_filter.link(payloader):
            raise RuntimeError(f"Failed to link capsfilter to payloader for camera {camera_id}")
        if not payloader.link(sink):
            raise RuntimeError(f"Failed to link payloader to udpsink for camera {camera_id}")
        caps_filter.sync_state_with_parent()
        payloader.sync_state_with_parent()
        sink.sync_state_with_parent()

        stream_name = str(camera_id)
        factory = GstRtspServer.RTSPMediaFactory()
        # name=pay0 required by GstRtspServer's SDP generation -- see
        # stream_server.py's own hardware-confirmed note.
        factory.set_launch(
            f'( udpsrc name=pay0 port={udp_port} caps="application/x-rtp, media=video, '
            f'clock-rate=90000, encoding-name=H264, payload=96" )'
        )
        factory.set_shared(True)
        self._server.get_mount_points().add_factory(f"/{stream_name}", factory)

        self._published[camera_id] = {
            "caps_filter": caps_filter,
            "payloader": payloader,
            "sink": sink,
            "udp_port": udp_port,
            "stream_name": stream_name,
        }
        logger.info(
            "Published camera %s media endpoint: rtsp://%s:%s/%s (subsystem=%s)",
            camera_id,
            self._host,
            self._rtsp_port,
            stream_name,
            self._subsystem,
        )
        return self._endpoint_for(camera_id)

    def unpublish(self, camera_id: uuid.UUID) -> None:
        """Idempotent -- a no-op for an already-unpublished (or never
        published) camera."""
        entry = self._published.pop(camera_id, None)
        if entry is None:
            return
        Gst = _import_gst()
        if self._server is not None:
            self._server.get_mount_points().remove_factory(f"/{entry['stream_name']}")
        # Sink-to-source, this module's own three-element chain -- same
        # ordering discipline as every other pipeline teardown in this
        # codebase (removing an upstream element while its downstream
        # neighbor is still PLAYING is the hardware-confirmed freeze
        # class of bug documented elsewhere in this repo).
        entry["sink"].set_state(Gst.State.NULL)
        entry["payloader"].set_state(Gst.State.NULL)
        entry["caps_filter"].set_state(Gst.State.NULL)
        self._pipeline.remove(entry["sink"])
        self._pipeline.remove(entry["payloader"])
        self._pipeline.remove(entry["caps_filter"])

    def stop(self) -> None:
        """Safe to call multiple times and safe to call when never started."""
        for camera_id in list(self._published):
            self.unpublish(camera_id)
        if self._server_source_id is not None:
            GLib = _import_glib()
            GLib.source_remove(self._server_source_id)
        self._server = None
        self._server_source_id = None

    def _endpoint_for(self, camera_id: uuid.UUID) -> MediaEndpoint:
        entry = self._published[camera_id]
        return MediaEndpoint(
            camera_id=camera_id,
            subsystem=self._subsystem,
            transport="rtsp",
            address=f"rtsp://{self._host}:{self._rtsp_port}/{entry['stream_name']}",
        )


def build_rtsp_source_element(endpoint: MediaEndpoint) -> Any:
    """A ``Gst.Bin`` with one ghost ``"src"`` pad: ``rtspsrc -> depay ->
    h264parse``. GLib main-loop thread only (construction). ``rtspsrc``
    has no static src pad -- its pad only exists once the RTSP session
    negotiates, so the ghost pad's target is set from the ``"pad-added"``
    callback, mirroring ``apps/deepstream/app/ingestion/source.py``'s
    proven shape exactly."""
    Gst = _import_gst()

    bin_ = Gst.Bin.new(f"media-source-{endpoint.camera_id}")
    rtspsrc = Gst.ElementFactory.make("rtspsrc", f"media-rtspsrc-{endpoint.camera_id}")
    depay = Gst.ElementFactory.make("rtph264depay", f"media-depay-{endpoint.camera_id}")
    parse = Gst.ElementFactory.make("h264parse", f"media-parse-{endpoint.camera_id}")
    for name, element in (("rtspsrc", rtspsrc), ("rtph264depay", depay), ("h264parse", parse)):
        if element is None:
            raise RuntimeError(f"Failed to create GStreamer element {name!r}")
        bin_.add(element)

    rtspsrc.set_property("location", endpoint.address)
    rtspsrc.set_property("protocols", "tcp")
    rtspsrc.set_property("latency", 200)
    rtspsrc.set_property("tcp-timeout", 5_000_000)  # 5s -- see module docstring

    depay.link(parse)

    def _on_pad_added(_element: Any, pad: Any) -> None:
        sink_pad = depay.get_static_pad("sink")
        if not sink_pad.is_linked():
            pad.link(sink_pad)

    rtspsrc.connect("pad-added", _on_pad_added)

    ghost_pad = Gst.GhostPad.new("src", parse.get_static_pad("src"))
    bin_.add_pad(ghost_pad)
    return bin_
