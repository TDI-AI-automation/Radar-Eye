"""Shared publisher lifecycle -- RM-12 Camera Runtime Step 7.

``_TieredPublisher`` owns everything Tier 1 and Tier 2 publishers share:
the ``ConsumerRegistry``, and attach/detach/register/unregister/shutdown.
Subclasses supply only *how to find the pad to probe* for a given camera
(``_find_pad``) and *how to deliver a buffer to one consumer*
(``_deliver``) -- the physical pad-probe attach/detach itself is always
scheduled through ``AsyncBridge.schedule_on_mainloop``, matching Step 3's
"every pipeline mutation happens on the GLib thread" discipline exactly
(adding/removing a pad probe mutates the pipeline's object graph, the same
category of operation as a valve's ``set_property``).

``register``/``unregister`` are pure bookkeeping (no Gst interaction, no
thread hop needed) -- a consumer can be registered before ``attach()`` is
ever called; it simply receives nothing until the probe is physically
attached. This mirrors Runtime Supervisor's own separation between
"intent" and "convergence": registering a consumer expresses intent to
receive frames, attaching is what makes that physically true.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Generic, Protocol, TypeVar

from apps.deepstream.app.media_publisher.registry import ConsumerRegistry

logger = logging.getLogger(__name__)

ConsumerT = TypeVar("ConsumerT")


def _import_gst() -> Any:
    import gi  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: PLC0415

    return Gst


class MediaPublisherError(RuntimeError):
    """Raised by ``attach()`` when the pad this publisher needs to probe
    doesn't exist for the given camera (e.g. no active source, or -- Tier
    2 -- the camera hasn't been added to the demux branch yet). Distinct
    from a *consumer's* own failure, which ``ConsumerRegistry.dispatch``
    isolates instead of raising."""


class GstBridge(Protocol):
    """The one thing publishers need from ``AsyncBridge`` -- kept as a
    narrow Protocol (matching every other Camera Runtime component's
    dependency style) rather than a concrete-class dependency."""

    def schedule_on_mainloop(self, func: Any) -> Any: ...


class _TieredPublisher(Generic[ConsumerT]):
    def __init__(self, bridge: GstBridge) -> None:
        self._bridge = bridge
        self.registry: ConsumerRegistry[ConsumerT] = ConsumerRegistry()
        self._probe_ids: dict[uuid.UUID, int] = {}

    def register(self, camera_id: uuid.UUID, consumer: ConsumerT) -> None:
        self.registry.register(camera_id, consumer)

    def unregister(self, camera_id: uuid.UUID, consumer: ConsumerT) -> None:
        self.registry.unregister(camera_id, consumer)

    def is_attached(self, camera_id: uuid.UUID) -> bool:
        return camera_id in self._probe_ids

    async def attach(self, camera_id: uuid.UUID) -> None:
        """Idempotent: attaching an already-attached camera is a no-op."""
        if camera_id in self._probe_ids:
            return
        future = self._bridge.schedule_on_mainloop(lambda: self._do_attach(camera_id))
        probe_id = await asyncio.wrap_future(future)
        self._probe_ids[camera_id] = probe_id

    async def detach(self, camera_id: uuid.UUID) -> None:
        """Idempotent: detaching an already-detached (or never-attached)
        camera is a no-op."""
        probe_id = self._probe_ids.pop(camera_id, None)
        if probe_id is None:
            return
        future = self._bridge.schedule_on_mainloop(lambda: self._do_detach(camera_id, probe_id))
        await asyncio.wrap_future(future)

    async def shutdown(self) -> None:
        """Detaches every currently-attached camera. Registered consumers
        are left registered (harmless once detached -- they simply stop
        receiving frames); callers that also want a clean registry should
        call ``unregister`` themselves first if that matters to them."""
        for camera_id in list(self._probe_ids):
            await self.detach(camera_id)

    def _do_attach(self, camera_id: uuid.UUID) -> int:
        """Runs on the GLib main-loop thread."""
        Gst = _import_gst()
        pad = self._find_pad(camera_id)
        if pad is None:
            raise MediaPublisherError(f"No pad to attach for camera {camera_id}")
        return pad.add_probe(Gst.PadProbeType.BUFFER, self._probe_callback, camera_id)

    def _do_detach(self, camera_id: uuid.UUID, probe_id: int) -> None:
        """Runs on the GLib main-loop thread. If the pad no longer exists
        (e.g. the camera's source was already torn down), there is nothing
        left to remove a probe from -- not an error, the probe went away
        with the pad."""
        pad = self._find_pad(camera_id)
        if pad is not None:
            pad.remove_probe(probe_id)

    def _probe_callback(self, _pad: Any, info: Any, camera_id: uuid.UUID) -> Any:
        """Runs on a GStreamer streaming thread."""
        Gst = _import_gst()
        gst_buffer = info.get_buffer()
        if gst_buffer is not None:
            self.registry.dispatch(
                camera_id, lambda consumer: self._deliver(consumer, camera_id, gst_buffer)
            )
        return Gst.PadProbeReturn.OK

    def _find_pad(self, camera_id: uuid.UUID) -> Any | None:
        raise NotImplementedError

    def _deliver(self, consumer: ConsumerT, camera_id: uuid.UUID, gst_buffer: Any) -> None:
        raise NotImplementedError
