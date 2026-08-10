"""Tests for
apps.deepstream.app.live_stream.consumer.BitstreamAppsrcBridge -- Live
Monitoring (WebRTC) Stage B.

Pure Python -- no DeepStream/GStreamer SDK needed. Fake appsrc/pad/buffer
objects record calls the same way test_media_publisher_base.py's FakePad
does, since BitstreamAppsrcBridge only ever calls a small, fixed surface
(``get_current_caps``, ``set_property``, ``emit``, ``get_size``) on real
Gst objects.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.deepstream.app.live_stream.consumer import BitstreamAppsrcBridge


class FakeCaps:
    pass


class FakeSourcePad:
    def __init__(self, caps: Any | None = None) -> None:
        self._caps = caps

    def get_current_caps(self) -> Any | None:
        return self._caps


class FakeBuffer:
    def __init__(self, name: str, size: int = 1024) -> None:
        self.name = name
        self._size = size

    def get_size(self) -> int:
        return self._size

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeBuffer) and other.name == self.name

    def __repr__(self) -> str:
        return f"FakeBuffer({self.name!r})"


class FakeAppsrc:
    def __init__(self) -> None:
        self.properties: dict[str, Any] = {}
        self.pushed_buffers: list[Any] = []

    def set_property(self, name: str, value: Any) -> None:
        self.properties[name] = value

    def emit(self, signal_name: str, buffer: Any) -> None:
        assert signal_name == "push-buffer"
        self.pushed_buffers.append(buffer)


class TestSetAndRemoveAppsrc:
    def test_set_appsrc_registers_camera(self) -> None:
        bridge = BitstreamAppsrcBridge()
        camera_id = uuid.uuid4()
        appsrc = FakeAppsrc()
        source_pad = FakeSourcePad(FakeCaps())

        bridge.set_appsrc(camera_id, appsrc, source_pad)
        bridge.on_encoded_frame(camera_id, FakeBuffer("au-1"))

        assert appsrc.pushed_buffers == [FakeBuffer("au-1")]

    def test_remove_appsrc_stops_delivery(self) -> None:
        bridge = BitstreamAppsrcBridge()
        camera_id = uuid.uuid4()
        appsrc = FakeAppsrc()
        source_pad = FakeSourcePad(FakeCaps())
        bridge.set_appsrc(camera_id, appsrc, source_pad)

        bridge.remove_appsrc(camera_id)
        bridge.on_encoded_frame(camera_id, FakeBuffer("au-1"))

        assert appsrc.pushed_buffers == []

    def test_remove_appsrc_for_unknown_camera_is_a_no_op(self) -> None:
        bridge = BitstreamAppsrcBridge()
        bridge.remove_appsrc(uuid.uuid4())  # must not raise


class TestOnEncodedFrame:
    def test_frame_for_unregistered_camera_is_ignored(self) -> None:
        bridge = BitstreamAppsrcBridge()
        bridge.on_encoded_frame(uuid.uuid4(), FakeBuffer("au-1"))  # must not raise

    def test_caps_are_set_once_from_the_first_negotiated_frame(self) -> None:
        bridge = BitstreamAppsrcBridge()
        camera_id = uuid.uuid4()
        appsrc = FakeAppsrc()
        caps = FakeCaps()
        source_pad = FakeSourcePad(caps)
        bridge.set_appsrc(camera_id, appsrc, source_pad)

        bridge.on_encoded_frame(camera_id, FakeBuffer("au-1"))
        bridge.on_encoded_frame(camera_id, FakeBuffer("au-2"))

        assert appsrc.properties["caps"] is caps
        assert appsrc.pushed_buffers == [FakeBuffer("au-1"), FakeBuffer("au-2")]

    def test_frame_is_skipped_while_caps_are_not_yet_negotiated(self) -> None:
        """source_pad.get_current_caps() returns None until the real RTSP
        stream's h264parse negotiates a format -- access units arriving
        before that must be dropped, not pushed into an appsrc with no
        caps."""
        bridge = BitstreamAppsrcBridge()
        camera_id = uuid.uuid4()
        appsrc = FakeAppsrc()
        source_pad = FakeSourcePad(caps=None)
        bridge.set_appsrc(camera_id, appsrc, source_pad)

        bridge.on_encoded_frame(camera_id, FakeBuffer("au-1"))

        assert appsrc.pushed_buffers == []
        assert "caps" not in appsrc.properties

    def test_push_buffer_exception_is_isolated_per_camera(self) -> None:
        """Matches ConsumerRegistry's own failure-isolation guarantee --
        one camera's appsrc failing to accept a buffer must not raise out
        of on_encoded_frame (a BitstreamFrameConsumer callback, invoked
        directly on a GStreamer streaming thread that must never be
        interrupted by an unhandled exception)."""

        class RaisingAppsrc(FakeAppsrc):
            def emit(self, signal_name: str, buffer: Any) -> None:
                raise RuntimeError("appsrc in the wrong state")

        bridge = BitstreamAppsrcBridge()
        camera_id = uuid.uuid4()
        appsrc = RaisingAppsrc()
        source_pad = FakeSourcePad(FakeCaps())
        bridge.set_appsrc(camera_id, appsrc, source_pad)

        bridge.on_encoded_frame(camera_id, FakeBuffer("au-1"))  # must not raise

    def test_two_cameras_are_tracked_independently(self) -> None:
        bridge = BitstreamAppsrcBridge()
        camera_a = uuid.uuid4()
        camera_b = uuid.uuid4()
        appsrc_a = FakeAppsrc()
        appsrc_b = FakeAppsrc()
        bridge.set_appsrc(camera_a, appsrc_a, FakeSourcePad(FakeCaps()))
        bridge.set_appsrc(camera_b, appsrc_b, FakeSourcePad(FakeCaps()))

        bridge.on_encoded_frame(camera_a, FakeBuffer("au-a"))
        bridge.on_encoded_frame(camera_b, FakeBuffer("au-b"))

        assert appsrc_a.pushed_buffers == [FakeBuffer("au-a")]
        assert appsrc_b.pushed_buffers == [FakeBuffer("au-b")]
