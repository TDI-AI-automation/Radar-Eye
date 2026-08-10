"""Tests for apps.deepstream.app.pipeline.builder.DeepStreamPipeline's
_attach_first_buffer_probe -- Observed-State-accuracy fix: a camera must
not be marked CONNECTED until a real buffer is confirmed flowing from it,
not merely once its GStreamer elements have been constructed and linked
(add_source() succeeding says nothing about whether rtspsrc has actually
finished its RTSP handshake with the camera).

Requires the real DeepStream/GStreamer SDK, matching this repo's
established convention (test_source.py, test_bitstream_publisher.py) --
skipped, not failed, when unavailable.

Deliberately does not reuse ingestion.source.build_source_bin(): that
bin's bitstream tee also feeds nvv4l2decoder, which errors on synthetic
(non-H.264) buffers. This test only needs to exercise
_attach_first_buffer_probe's own attach/fire/one-shot-removal logic, so
it wires a minimal standalone bin -- appsrc -> tee (named exactly like
the real bitstream tee) -> fakesink -- with no decoder involved at all.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from apps.deepstream.app.pipeline.builder import DeepStreamPipeline  # noqa: E402
from apps.deepstream.app.pipeline.frame_distributor import (  # noqa: E402
    bitstream_tee_element_name,
)

Gst.init(None)


def _missing_plugins() -> list[str]:
    return [name for name in ("appsrc", "tee", "fakesink") if Gst.ElementFactory.find(name) is None]


@pytest.fixture(autouse=True)
def _require_gst_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer plugin(s) not installed on this machine: {missing}")


def _make_pipeline(on_source_first_buffer: Any) -> DeepStreamPipeline:
    """A DeepStreamPipeline instance carrying only the one field
    _attach_first_buffer_probe actually reads -- avoids constructing the
    full settings/models/streammux graph, which this method never
    touches (matches this method's own "Gst = _import_gst()" deferred
    style: nothing else about the class is exercised)."""
    pipeline = object.__new__(DeepStreamPipeline)
    pipeline._on_source_first_buffer = on_source_first_buffer  # type: ignore[attr-defined]
    return pipeline


def _make_bin_with_bitstream_tee(camera_id: uuid.UUID) -> tuple[Any, Any]:
    """A real ``Gst.Pipeline`` (not a bare ``Gst.Bin``) -- appsrc's
    ``push-buffer`` hands off to a GStreamer streaming thread, which
    needs a real pipeline/bus/clock underneath it to actually run the
    buffer through the chain; a disconnected ``Gst.Bin`` never does."""
    pipeline = Gst.Pipeline.new(f"test-pipeline-{camera_id}")
    appsrc = Gst.ElementFactory.make("appsrc", f"src-{camera_id}")
    appsrc.set_property("caps", Gst.Caps.from_string("video/x-h264"))
    appsrc.set_property("format", Gst.Format.TIME)
    tee = Gst.ElementFactory.make("tee", bitstream_tee_element_name(camera_id))
    sink = Gst.ElementFactory.make("fakesink", f"sink-{camera_id}")
    sink.set_property("sync", False)
    sink.set_property("async", False)
    for element in (appsrc, tee, sink):
        pipeline.add(element)
    if not appsrc.link(tee):
        raise RuntimeError("Failed to link appsrc to test bitstream tee")
    branch_pad = tee.get_request_pad("src_%u")
    if branch_pad.link(sink.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Failed to link test bitstream tee to fakesink")
    return pipeline, appsrc


def _push(appsrc: Any) -> None:
    assert appsrc.emit("push-buffer", Gst.Buffer.new_allocate(None, 4, None)) == Gst.FlowReturn.OK


class TestAttachFirstBufferProbe:
    def test_fires_callback_exactly_once_on_first_real_buffer(self) -> None:
        camera_id = uuid.uuid4()
        fired = threading.Event()
        seen: list[uuid.UUID] = []

        def on_first_buffer(cid: uuid.UUID) -> None:
            seen.append(cid)
            fired.set()

        pipeline = _make_pipeline(on_first_buffer)
        bin_, appsrc = _make_bin_with_bitstream_tee(camera_id)

        pipeline._attach_first_buffer_probe(bin_, camera_id)
        try:
            bin_.set_state(Gst.State.PLAYING)
            bin_.get_state(Gst.CLOCK_TIME_NONE)

            _push(appsrc)
            assert fired.wait(timeout=5.0), "on_source_first_buffer never fired"
            assert seen == [camera_id]

            # One-shot: a second buffer must not fire the callback again.
            _push(appsrc)
            _push(appsrc)
            assert seen == [camera_id]
        finally:
            bin_.set_state(Gst.State.NULL)

    def test_no_op_when_no_callback_supplied(self) -> None:
        camera_id = uuid.uuid4()
        pipeline = _make_pipeline(None)
        bin_, appsrc = _make_bin_with_bitstream_tee(camera_id)

        pipeline._attach_first_buffer_probe(bin_, camera_id)  # must not raise
        try:
            bin_.set_state(Gst.State.PLAYING)
            bin_.get_state(Gst.CLOCK_TIME_NONE)
            _push(appsrc)  # must not raise either
        finally:
            bin_.set_state(Gst.State.NULL)

    def test_no_op_when_bitstream_tee_is_absent(self) -> None:
        """A stub/unit-test bin without a bitstream tee at all (e.g. a
        different unit test's fake pipeline) must not error -- matches
        _find_pad's own None-safe convention in media_publisher/base.py."""
        camera_id = uuid.uuid4()
        seen: list[uuid.UUID] = []
        pipeline = _make_pipeline(seen.append)
        bin_ = Gst.Bin.new("empty-bin")

        pipeline._attach_first_buffer_probe(bin_, camera_id)  # must not raise

        assert seen == []
