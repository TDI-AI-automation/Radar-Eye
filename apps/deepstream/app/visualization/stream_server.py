"""RtspStreamServer -- publishes the visualization branch's already-encoded
H.264/RTP stream over RTSP, RM-11.SIV.

Deliberately separate from ``pipeline_builder.py``: this class only wraps
``GstRtspServer`` and knows nothing about how the UDP stream it proxies was
produced -- ``VisualizationPipelineBuilder`` builds
``... -> rtph264pay -> udpsink`` and hands this class the port number, no
more. Proxies the already-encoded stream via a ``udpsrc``-wrapping media
factory (the established DeepStream reference-app RTSP-out pattern) rather
than re-encoding per client; ``set_shared(True)`` means multiple
simultaneous VLC clients share one relay instead of independent work --
"encode once."

``start()`` is called from the same (asyncio) thread that builds the
pipeline, before ``AsyncBridge`` spawns the GLib-mainloop thread -- verified
safe: neither ``Gst.init()`` nor ``AsyncBridge``'s ``GLib.MainLoop()`` pass
an explicit ``GMainContext``, so both use the process's single default
context, and GLib source attachment is internally thread-safe. See
docs/DEEPSTREAM_PIPELINE_SPEC.md's Visualization Path section.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RtspServerHealth:
    """Only fields this implementation can populate correctly -- no
    ``client_count``/``last_frame_timestamp``/``last_publish_timestamp``,
    which would require wiring ``GstRtspServer`` client-connected signals
    and additional timestamp bookkeeping this milestone doesn't need. A
    frozen dataclass is additive-safe: new fields can be appended later
    with defaults without breaking any current caller."""

    running: bool
    bound_port: int | None
    stream_name: str
    reason: str | None


class RtspStreamServer:
    def __init__(self, *, udp_port: int, rtsp_port: int, stream_name: str) -> None:
        self._udp_port = udp_port
        self._rtsp_port = rtsp_port
        self._stream_name = stream_name
        self._server: Any = None
        self._source_id: int | None = None
        self._running = False
        self._reason: str | None = None

    def start(self) -> None:
        """Raises on failure (e.g. ``rtsp_port`` already bound by another
        process) -- the caller (``VisualizationManager.start()``, called
        from ``builder.py``'s failure-isolation ``try/except``) is expected
        to catch it, same shared path as every other visualization
        construction failure."""
        GstRtspServer, _Gst = _import_gst_rtsp_server()

        server = GstRtspServer.RTSPServer()
        server.set_service(str(self._rtsp_port))

        factory = GstRtspServer.RTSPMediaFactory()
        # name=pay0 is required, not cosmetic -- GstRtspServer's SDP
        # generation specifically looks for an element named pay0 (or
        # pay%d for multiple streams) to identify the payload source; a
        # bare unnamed udpsrc attaches successfully (attach() only proves
        # the server bound its port) but a real client's DESCRIBE/SETUP
        # then fails with "SDP contains no streams" -- caught via a real
        # gst-launch-1.0 RTSP client during Phase 5 hardware verification,
        # not visible in the manager-level smoke tests from Phase 3.
        #
        # buffer-size=2097152: this udpsrc's default kernel receive buffer
        # (unset -> OS default, 212992 bytes on this reference machine) is
        # smaller than a single H.264 IDR frame's RTP packet burst at
        # viz-encoder's bitrate/iframeinterval -- confirmed by a targeted
        # loopback-socket reproduction (send a ~300KB burst matching one
        # keyframe with the reader briefly behind, as under real GPU/CPU
        # load): 56% of packets dropped to the kernel's UdpRcvbufErrors
        # counter at the default size, vs. ~14% once the receive buffer is
        # sized to hold a full keyframe burst. Those dropped RTP packets
        # corrupt whatever macroblocks they carried; since the affected
        # regions are typically static background (skip-coded across
        # P-frames), the corruption persists on screen until the next
        # keyframe fully refreshes it -- the observed ~1s ghosting/
        # blockiness cycle (iframeinterval is one keyframe/sec). Sized well
        # above one keyframe's worth of RTP packets at this bitrate; also
        # bounded by net.core.rmem_max at deployment (should be raised
        # alongside this for full effect on the Jetson target).
        factory.set_launch(
            f"( udpsrc name=pay0 port={self._udp_port} buffer-size=2097152 "
            f'caps="application/x-rtp, media=video, '
            f'clock-rate=90000, encoding-name=H264, payload=96" )'
        )
        factory.set_shared(True)
        server.get_mount_points().add_factory(f"/{self._stream_name}", factory)

        source_id = server.attach(None)
        if source_id == 0:
            raise RuntimeError(
                f"Failed to attach RTSP server on port {self._rtsp_port} "
                "(already in use by another process?)"
            )

        self._server = server
        self._source_id = source_id
        self._running = True
        self._reason = None

    def stop(self) -> None:
        """Safe to call multiple times and safe to call when never
        started."""
        if self._source_id is not None:
            GLib = _import_glib()
            GLib.source_remove(self._source_id)
        self._server = None
        self._source_id = None
        self._running = False

    def health(self) -> RtspServerHealth:
        return RtspServerHealth(
            running=self._running,
            bound_port=self._rtsp_port if self._running else None,
            stream_name=self._stream_name,
            reason=self._reason,
        )


def _import_gst_rtsp_server() -> tuple[Any, Any]:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    gi.require_version("GstRtspServer", "1.0")
    from gi.repository import Gst, GstRtspServer  # noqa: PLC0415

    return GstRtspServer, Gst


def _import_glib() -> Any:
    import gi  # noqa: PLC0415

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib  # noqa: PLC0415

    return GLib
