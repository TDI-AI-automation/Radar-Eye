"""LiveStreamingRuntime -- Live Streaming Service's top-level orchestrator.

Owns: the shared ``Gst.Pipeline`` (one process, N independent per-camera
local ``rtspsrc`` subscriptions -- no shared muxer, no batching, exactly
like Camera Ingestion's own shape), the endpoint-roster poll loop (reads
``camera_media_endpoints`` where ``subsystem="ingestion"`` -- never the
camera registry, never credentials), reconnect policy per camera, one
``WebRtcBranch`` per camera, and the signaling server that dispatches
browser SDP offers to them.

Structurally mirrors ``apps.ingestion.app.runtime.IngestionRuntime``
(same three-way split: roster-diff sync loop, per-camera reconnect-on-
bus-error loop, per-camera health reporting) -- both are "GStreamer-
owning process with N independent per-camera subscriptions" at heart,
differing only in *what* they subscribe to (a real camera's RTSP
session with credentials, vs. an already-published, credential-free
``MediaEndpoint``) and what they build per camera (an ingest bin + RTSP
republish, vs. a subscriber bin + WebRTC branch). This mirroring is
deliberate, not duplication-by-accident: it is what "Camera Ingestion
and Live Streaming are independently-lifecycled, structurally similar
platform services" (ADR-028) looks like in code.

Observed-State-accuracy discipline reused again (see IngestionRuntime's
own docstring for the original root-cause): a camera is marked
RECONNECTING (not CONNECTED) the moment its subscriber bin is built --
only a one-shot first-buffer probe promotes it to CONNECTED.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from apps.api.app.repositories.media import (
    CameraMediaEndpointRepository,
    CameraSubsystemHealthRepository,
)
from apps.live_stream.app.config import LiveStreamingSettings
from shared.gst_bridge import AsyncBridge
from shared.media_transport.interface import MediaEndpoint, build_source_element
from shared.media_transport.webrtc import WebRtcBranch
from shared.media_transport.webrtc_signaling import WebRtcSignalingServer
from shared.reconnect import ReconnectPolicy

logger = logging.getLogger(__name__)

_SUBSYSTEM = "live_streaming"


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    Gst.init(None)
    return Gst


@dataclass
class _Subscription:
    """One camera's active local subscription: the subscriber bin
    (``rtspsrc -> depay -> h264parse -> [ghost pad]``, from
    ``build_source_element()``) feeding a permanent split ``tee`` --
    ``drain`` (a leaky queue -> fakesink, always linked, so the
    subscription keeps flowing whether or not any browser is currently
    connected) plus, per browser connection, a ``WebRtcBranch`` that
    dynamically requests its own tee branch (see ``_build_and_wire``'s
    docstring for why the drain branch exists at all). Owns no reconnect
    timing -- see ``LiveStreamingRuntime``."""

    endpoint: MediaEndpoint
    bin: Any = None
    tee: Any = None
    drain_elements: list[Any] = field(default_factory=list)
    branch: WebRtcBranch | None = None

    @property
    def camera_id(self) -> uuid.UUID:
        return self.endpoint.camera_id

    def is_failure_message(self, message: Any) -> bool:
        Gst = _import_gst()
        if message.type not in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
            return False
        src = message.src
        return self.bin is not None and bool(src) and self._owns(src)

    def _owns(self, element: Any) -> bool:
        parent = element
        while parent is not None:
            if parent == self.bin:
                return True
            parent = parent.get_parent()
        return False


class LiveStreamingRuntime:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        settings: LiveStreamingSettings,
        session_factory: Any,
    ) -> None:
        self._loop = loop
        self._settings = settings
        self._session_factory = session_factory

        self._bridge = AsyncBridge(loop)
        self._pipeline: Any = None
        self._signaling_server: WebRtcSignalingServer | None = None

        self._sources: dict[uuid.UUID, _Subscription] = {}
        self._policies: dict[uuid.UUID, ReconnectPolicy] = {}
        self._sync_task: asyncio.Task[None] | None = None
        self._running = False

        self.on_first_rtp_packet: Callable[[uuid.UUID], None] | None = None
        """Optional hook, called (off the GLib thread, via the bridge)
        the first time any browser connection's RTP payloader pushes a
        buffer for a given camera -- latency instrumentation attaches
        here rather than this class hardcoding any measurement."""

    # -- Startup / shutdown ------------------------------------------------

    async def start(self) -> None:
        Gst = _import_gst()
        self._pipeline = Gst.Pipeline.new("radar-eye-live-streaming")
        self._bridge.start()

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        await asyncio.wrap_future(
            self._bridge.schedule_on_mainloop(lambda: self._pipeline.set_state(Gst.State.PLAYING))
        )

        self._signaling_server = WebRtcSignalingServer(
            self, host=self._settings.signaling_host, port=self._settings.signaling_port
        )
        await self._signaling_server.start()

        self._running = True
        await self._synchronize()
        self._sync_task = self._loop.create_task(self._synchronize_forever())
        logger.info(
            "Live Streaming signaling listening on %s:%s",
            self._settings.signaling_host,
            self._settings.signaling_port,
        )

    async def stop(self) -> None:
        self._running = False
        if self._sync_task is not None:
            self._sync_task.cancel()
            self._sync_task = None
        for camera_id in list(self._sources):
            await self._remove_camera(camera_id)
        if self._signaling_server is not None:
            await self._signaling_server.stop()
            self._signaling_server = None
        if self._pipeline is not None:
            Gst = _import_gst()
            await asyncio.wrap_future(
                self._bridge.schedule_on_mainloop(lambda: self._pipeline.set_state(Gst.State.NULL))
            )
        self._bridge.stop()

    # -- Endpoint roster convergence ----------------------------------------

    async def _synchronize_forever(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._settings.desired_state_poll_interval_seconds)
                try:
                    await self._synchronize()
                except Exception:
                    logger.exception("Live Streaming synchronize() failed")
        except asyncio.CancelledError:
            pass

    async def _synchronize(self) -> None:
        async with self._session_factory() as session:
            rows = await CameraMediaEndpointRepository(session).list_by_subsystem(
                self._settings.upstream_subsystem
            )

        desired_by_id = {
            row.camera_id: MediaEndpoint(
                camera_id=row.camera_id,
                subsystem=row.subsystem,
                transport=row.transport,
                address=row.address,
            )
            for row in rows
        }

        for camera_id in list(self._sources):
            if camera_id not in desired_by_id:
                await self._remove_camera(camera_id)

        for camera_id, endpoint in desired_by_id.items():
            if camera_id not in self._sources:
                await self._add_camera(endpoint)

    async def _add_camera(self, endpoint: MediaEndpoint) -> None:
        subscription = _Subscription(endpoint=endpoint)
        self._sources[endpoint.camera_id] = subscription
        self._policies[endpoint.camera_id] = ReconnectPolicy(
            initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
            max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
            multiplier=self._settings.reconnect_backoff_multiplier,
        )
        await self._build_and_wire(subscription)
        await self._set_health(endpoint.camera_id, status="RECONNECTING", detail=None)

    async def _build_and_wire(self, subscription: _Subscription) -> None:
        """Builds the subscriber bin plus a permanent split tee with a
        drain branch (leaky queue -> fakesink), then a WebRtcBranch
        aimed at the tee -- not the bin directly.

        The drain branch is required, not optional: a browser may not
        connect for an arbitrary time (or ever) after this subscription
        starts, but the subscriber bin's own upstream (rtspsrc) is live
        and starts pushing the moment it's PLAYING. A live source whose
        downstream chain ends in an unlinked pad gets a fatal
        GST_FLOW_NOT_LINKED the first time it tries to push through it
        -- hardware-confirmed against the real republished endpoint: the
        camera's own rtspsrc reconnect-looped indefinitely with
        "streaming stopped, reason not-linked" every single time, since
        nothing was linked to the subscriber bin's ghost pad until a
        browser happened to call handle_offer(). The permanent drain
        keeps the tee (and everything upstream of it) satisfied
        regardless of browser connections; WebRtcBranch's own per-
        connection payloader is just another tee branch, requested
        fresh (Element.link()'s auto-request) only once a browser
        actually connects -- dynamically, after the pipeline is already
        PLAYING, which avoids a second, unrelated GStreamer tee quirk
        found writing this module's own tests: a request pad activated
        while still unlinked (i.e. requested up front, before PLAYING)
        never pushes a single buffer even once linked later, despite
        the link itself succeeding structurally.
        """

        def _build_on_mainloop() -> None:
            Gst = _import_gst()
            bin_ = build_source_element(subscription.endpoint)
            self._pipeline.add(bin_)
            bin_.sync_state_with_parent()
            subscription.bin = bin_
            self._attach_first_buffer_probe(subscription.camera_id, bin_)

            tee = Gst.ElementFactory.make("tee", f"live-split-{subscription.camera_id}")
            drain_queue = Gst.ElementFactory.make(
                "queue", f"live-drain-queue-{subscription.camera_id}"
            )
            drain_queue.set_property("leaky", 2)  # downstream: drop oldest, never block
            drain_queue.set_property("max-size-buffers", 4)
            drain_queue.set_property("max-size-bytes", 0)
            drain_queue.set_property("max-size-time", 0)
            drain_sink = Gst.ElementFactory.make(
                "fakesink", f"live-drain-sink-{subscription.camera_id}"
            )
            drain_sink.set_property("sync", False)
            drain_sink.set_property("async", False)
            for element in (tee, drain_queue, drain_sink):
                if element is None:
                    raise RuntimeError(
                        f"Failed to create Live Streaming split/drain element for camera "
                        f"{subscription.camera_id}"
                    )
                self._pipeline.add(element)
            if not bin_.link(tee):
                raise RuntimeError(
                    f"Failed to link subscriber bin to split tee for camera "
                    f"{subscription.camera_id}"
                )
            if not drain_queue.link(drain_sink):
                raise RuntimeError(
                    f"Failed to link drain queue to sink for camera {subscription.camera_id}"
                )
            if not tee.link(drain_queue):
                raise RuntimeError(
                    f"Failed to link split tee to drain queue for camera "
                    f"{subscription.camera_id}"
                )
            for element in (tee, drain_queue, drain_sink):
                element.sync_state_with_parent()
            subscription.tee = tee
            subscription.drain_elements = [drain_queue, drain_sink]

            subscription.branch = WebRtcBranch(
                self._pipeline,
                tee,
                subscription.camera_id,
                stun_servers=self._settings.stun_servers,
                bridge=self._bridge,
                loop=self._loop,
                on_first_rtp_packet=lambda: self._on_first_rtp_packet(subscription.camera_id),
            )

        await asyncio.wrap_future(self._bridge.schedule_on_mainloop(_build_on_mainloop))

    def _on_first_rtp_packet(self, camera_id: uuid.UUID) -> None:
        if self.on_first_rtp_packet is not None:
            self.on_first_rtp_packet(camera_id)

    def _attach_first_buffer_probe(self, camera_id: uuid.UUID, bin_: Any) -> None:
        """One-shot: promotes this camera to CONNECTED the moment a real
        buffer is observed at the subscriber bin's own ghost src pad --
        the earliest point that confirms the *local* subscription to
        Camera Ingestion's republished stream is actually delivering
        data (see module docstring)."""
        Gst = _import_gst()
        pad = bin_.get_static_pad("src")
        probe_id_holder: list[int] = []

        def _on_first_buffer(_pad: Any, _info: Any) -> Any:
            if probe_id_holder:
                pad.remove_probe(probe_id_holder[0])
            self._bridge.schedule(self._on_first_buffer(camera_id))
            return Gst.PadProbeReturn.OK

        probe_id_holder.append(pad.add_probe(Gst.PadProbeType.BUFFER, _on_first_buffer))

    async def _on_first_buffer(self, camera_id: uuid.UUID) -> None:
        policy = self._policies.get(camera_id)
        if policy is not None:
            policy.reset()
        await self._set_health(camera_id, status="CONNECTED", detail=None)

    async def _remove_camera(self, camera_id: uuid.UUID) -> None:
        subscription = self._sources.pop(camera_id, None)
        self._policies.pop(camera_id, None)
        if subscription is None:
            return

        await asyncio.wrap_future(
            self._bridge.schedule_on_mainloop(lambda: self._teardown(subscription))
        )
        await self._set_health(camera_id, status="DISCONNECTED", detail="endpoint removed")

    def _teardown(self, subscription: _Subscription) -> None:
        """GLib main-loop thread only. Sink-to-source: the WebRTC
        transport and the drain branch (both downstream of the split
        tee) tear down first, then the tee, then the subscriber bin
        itself -- same discipline as every other pipeline teardown in
        this codebase."""
        Gst = _import_gst()
        if subscription.branch is not None:
            subscription.branch.teardown()
            subscription.branch = None
        for element in reversed(subscription.drain_elements):
            element.set_state(Gst.State.NULL)
        for element in subscription.drain_elements:
            self._pipeline.remove(element)
        subscription.drain_elements = []
        if subscription.tee is not None:
            subscription.tee.set_state(Gst.State.NULL)
            self._pipeline.remove(subscription.tee)
            subscription.tee = None
        if subscription.bin is not None:
            subscription.bin.set_state(Gst.State.NULL)
            self._pipeline.remove(subscription.bin)
            subscription.bin = None

    # -- Failure handling ----------------------------------------------------

    def _on_bus_message(self, _bus: Any, message: Any) -> None:
        """Runs on the GLib main-loop thread. This is how a camera whose
        endpoint row is still present but whose *actual* local RTSP
        connection has failed (e.g. Camera Ingestion crashed without a
        clean shutdown, leaving a stale-but-present endpoint row) is
        detected -- the roster-diff sync loop alone cannot see this,
        since nothing removed the row."""
        subscription = self._subscription_for_message(message)
        if subscription is None:
            return
        Gst = _import_gst()
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            reason = f"{err} -- {debug}"
        else:
            reason = "end of stream"
        logger.warning(
            "Camera %s live streaming upstream failure: %s", subscription.camera_id, reason
        )
        self._bridge.schedule(self._handle_failure(subscription.camera_id, reason))

    def _subscription_for_message(self, message: Any) -> _Subscription | None:
        for subscription in self._sources.values():
            if subscription.is_failure_message(message):
                return subscription
        return None

    async def _handle_failure(self, camera_id: uuid.UUID, reason: str) -> None:
        subscription = self._sources.get(camera_id)
        if subscription is None:
            return
        await self._set_health(camera_id, status="DISCONNECTED", detail=reason)

        await asyncio.wrap_future(
            self._bridge.schedule_on_mainloop(lambda: self._teardown(subscription))
        )

        policy = self._policies.setdefault(
            camera_id,
            ReconnectPolicy(
                initial_backoff_seconds=self._settings.reconnect_initial_backoff_seconds,
                max_backoff_seconds=self._settings.reconnect_max_backoff_seconds,
                multiplier=self._settings.reconnect_backoff_multiplier,
            ),
        )
        delay = policy.next_delay_seconds()
        logger.info("Scheduling live streaming reconnect for camera %s in %.1fs", camera_id, delay)
        await asyncio.sleep(delay)
        if camera_id not in self._sources or not self._running:
            return  # camera's endpoint was removed (or we're shutting down) while waiting
        await self._set_health(camera_id, status="RECONNECTING", detail=None)
        await self._build_and_wire(subscription)

    async def _set_health(self, camera_id: uuid.UUID, *, status: str, detail: str | None) -> None:
        async with self._session_factory() as session:
            await CameraSubsystemHealthRepository(session).set_health(
                camera_id, _SUBSYSTEM, status=status, detail=detail
            )
            await session.commit()

    # -- OfferHandler protocol (shared.media_transport.webrtc_signaling) ----

    async def handle_offer(self, camera_id: uuid.UUID, sdp_offer_text: str) -> str:
        subscription = self._sources.get(camera_id)
        if subscription is None or subscription.branch is None:
            raise KeyError(camera_id)
        return await subscription.branch.handle_offer(sdp_offer_text)
