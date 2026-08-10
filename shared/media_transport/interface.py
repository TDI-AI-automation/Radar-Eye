"""The Media Distribution Interface's transport-agnostic contract.

Every cross-process media exchange in this codebase goes through
``MediaEndpoint``/``build_source_element()``. A consumer never
constructs a transport-specific element (``rtspsrc``, or a future
``shmsrc``/``srtsrc``) against a publisher's address directly -- it asks
for a camera's current endpoint (see each app's own ``desired_state``/
health-reading code, which reads ``camera_media_endpoints``, the same
Postgres-backed cross-process sharing mechanism already established for
Desired/Observed State) and hands that endpoint to
``build_source_element()``, which is the one place that knows how to
turn a descriptor into a real GStreamer source. Swapping the transport
later means changing ``rtsp.py`` (or adding a sibling module) and this
function's dispatch table -- no consumer changes.

Symmetric on the publish side: ``MediaPublisher`` is implemented once
per publishing process (Camera Ingestion for raw video; AI Runtime,
from Phase 5 onward, for annotated video) and hides how a camera's
encoded output actually gets exposed to other processes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MediaEndpoint:
    """Describes how to reach one camera's currently-published media --
    opaque to every consumer except the transport implementation named
    in ``transport``. Consumers never construct connection details
    themselves; they read this descriptor (from ``camera_media_endpoints``)
    and hand it to ``build_source_element()``."""

    camera_id: uuid.UUID
    subsystem: str
    """Which publishing subsystem produced this endpoint -- "ingestion"
    (raw video) or "ai" (annotated video, from Phase 5 onward). A camera
    can have more than one concurrently-published endpoint, one per
    subsystem; this field disambiguates which one a given row is."""
    transport: str
    """"rtsp" today (see rtsp.py) -- future: "shm"/"srt"/"udp"/etc."""
    address: str
    """Transport-specific connection string -- an RTSP URL today.
    Opaque to every caller except build_source_element()."""


class MediaPublisher(Protocol):
    """Implemented once per publishing process."""

    def publish(self, camera_id: uuid.UUID, source_pad: Any) -> MediaEndpoint:
        """Exposes ``source_pad``'s already-encoded H.264 output
        (elementary stream, matching whatever h264parse produces) to
        other processes, returning the resulting endpoint. Idempotent
        per camera_id -- publishing an already-published camera again
        is a no-op returning the existing endpoint."""
        ...

    def unpublish(self, camera_id: uuid.UUID) -> None:
        """Stops exposing camera_id's media. Idempotent -- unpublishing
        an already-unpublished (or never-published) camera is a no-op."""
        ...


def build_source_element(endpoint: MediaEndpoint) -> Any:
    """The one place that turns a ``MediaEndpoint`` into a real
    GStreamer source element (a ``Gst.Bin`` with one ghost ``"src"``
    pad producing the camera's encoded H.264 elementary stream).
    Dispatches on ``endpoint.transport`` -- every consumer calls only
    this function, never constructs a transport-specific source
    directly against ``endpoint.address``.
    """
    if endpoint.transport == "rtsp":
        from shared.media_transport.rtsp import build_rtsp_source_element  # noqa: PLC0415

        return build_rtsp_source_element(endpoint)
    raise NotImplementedError(f"Unknown media transport: {endpoint.transport!r}")
