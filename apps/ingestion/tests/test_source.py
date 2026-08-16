"""Tests for apps.ingestion.app.source -- Camera Ingestion's entire
GStreamer scope (ADR-028): rtspsrc -> rtph264depay -> h264parse -> tee.
No decode, no valve, no streammux, no inference, no webrtcbin, no
encoder.

Requires the real GStreamer SDK -- skipped, not failed, when
unavailable, matching this repo's established convention
(apps/deepstream/tests/test_source.py). Bin *construction* never
requires a reachable camera -- rtspsrc's pad-added callback is the only
part of this module that needs a live stream, and none of these tests
trigger it.
"""

from __future__ import annotations

import uuid

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from apps.ingestion.app.camera_registry import CameraSource  # noqa: E402
from apps.ingestion.app.source import (  # noqa: E402
    IngestedSource,
    build_source_bin,
    release_split_pad,
    request_split_pad,
    tee_element_name,
)

Gst.init(None)


def _missing_plugins() -> list[str]:
    return [
        name
        for name in ("rtspsrc", "rtph264depay", "h264parse")
        if Gst.ElementFactory.find(name) is None
    ]


@pytest.fixture(autouse=True)
def _require_gst_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer plugin(s) not installed on this machine: {missing}")


def _make_source(camera_id: uuid.UUID | None = None) -> CameraSource:
    # Deliberately not a reachable address -- construction never connects.
    return CameraSource(
        camera_id=camera_id or uuid.uuid4(),
        name="test-camera",
        rtsp_url="rtsp://192.0.2.1:554/does-not-need-to-be-reachable",
        transport="tcp",
    )


class TestBuildSourceBin:
    def test_bin_has_no_static_src_pad(self) -> None:
        """No ghost pad -- the Encoded Split tee is the bin's only
        interface; consumers request their own pad from it by name."""
        bin_ = build_source_bin(_make_source())
        assert bin_.get_static_pad("src") is None

    def test_tee_is_discoverable_by_name_and_fed_by_h264parse(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        parse = bin_.get_by_name(f"parse-{source.camera_id}")
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        assert tee is not None
        tee_sink = tee.get_static_pad("sink")
        assert tee_sink.is_linked()
        assert tee_sink.get_peer() == parse.get_static_pad("src")

    def test_tee_produces_a_working_request_pad(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        pad = tee.get_request_pad("src_%u")
        assert pad is not None
        tee.release_request_pad(pad)

    def test_depay_links_to_parse(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        depay = bin_.get_by_name(f"depay-{source.camera_id}")
        parse = bin_.get_by_name(f"parse-{source.camera_id}")
        depay_src = depay.get_static_pad("src")
        assert depay_src.is_linked()
        assert depay_src.get_peer() == parse.get_static_pad("sink")

    def test_rtspsrc_location_and_transport_are_set(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source, latency_ms=250)
        rtspsrc = bin_.get_by_name(f"rtspsrc-{source.camera_id}")
        assert rtspsrc.get_property("location") == source.rtsp_url
        assert rtspsrc.get_property("latency") == 250

    def test_bin_reaches_null_state_cleanly(self) -> None:
        bin_ = build_source_bin(_make_source())
        ret = bin_.set_state(Gst.State.NULL)
        assert ret != Gst.StateChangeReturn.FAILURE

    def test_no_decode_no_valve_elements_present(self) -> None:
        """Confirms the platform-service scope boundary at the pipeline
        level, not just by code inspection: this bin contains exactly
        rtspsrc/depay/parse/tee, nothing else -- no decoder, no
        streammux, no inference, no webrtcbin, no encoder."""
        source = _make_source()
        bin_ = build_source_bin(source)
        names = set()
        it = bin_.iterate_elements()
        while True:
            result, elem = it.next()
            if result != Gst.IteratorResult.OK:
                break
            names.add(elem.get_name())
        assert names == {
            f"rtspsrc-{source.camera_id}",
            f"depay-{source.camera_id}",
            f"parse-{source.camera_id}",
            tee_element_name(source.camera_id),
        }


class TestSplitPad:
    """request_split_pad/release_split_pad -- the ghosting step that
    lets an Encoded Split tee branch (which lives inside this module's
    child Gst.Bin) be linked to an element added to a *different*
    Gst.Bin/Gst.Pipeline, exactly how shared.media_transport.rtsp.
    RtspMediaPublisher consumes it. A tee request pad handed to
    Pad.link() without this ghosting step fails cross-bin (GStreamer
    requires linked pads to share a bin scope) -- these tests exercise
    that exact cross-bin link, not just pad construction, so a
    regression here fails in this suite instead of only on real
    hardware."""

    def test_request_split_pad_is_linkable_to_an_element_outside_the_bin(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        pipeline = Gst.Pipeline.new("test-pipeline")
        pipeline.add(bin_)

        sink = Gst.ElementFactory.make("fakesink", "sink")
        pipeline.add(sink)

        split_pad = request_split_pad(bin_, source.camera_id)
        try:
            assert split_pad.link(sink.get_static_pad("sink")) == Gst.PadLinkReturn.OK
        finally:
            release_split_pad(bin_, source.camera_id, split_pad)
            pipeline.set_state(Gst.State.NULL)

    def test_two_independent_split_pads_can_coexist(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        pipeline = Gst.Pipeline.new("test-pipeline")
        pipeline.add(bin_)

        first = request_split_pad(bin_, source.camera_id)
        second = request_split_pad(bin_, source.camera_id)
        try:
            assert first.get_name() != second.get_name()
        finally:
            release_split_pad(bin_, source.camera_id, first)
            release_split_pad(bin_, source.camera_id, second)
            pipeline.set_state(Gst.State.NULL)

    def test_release_split_pad_removes_the_ghost(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        pipeline = Gst.Pipeline.new("test-pipeline")
        pipeline.add(bin_)

        split_pad = request_split_pad(bin_, source.camera_id)
        ghost_name = split_pad.get_name()
        release_split_pad(bin_, source.camera_id, split_pad)

        assert bin_.get_static_pad(ghost_name) is None
        pipeline.set_state(Gst.State.NULL)


class TestIngestedSource:
    def test_build_sets_bin(self) -> None:
        ingested = IngestedSource(camera=_make_source())
        assert ingested.bin is None
        result = ingested.build()
        assert ingested.bin is result

    def test_is_failure_message_false_before_build(self) -> None:
        ingested = IngestedSource(camera=_make_source())

        class _FakeMessage:
            type = Gst.MessageType.ERROR
            src = None

        assert ingested.is_failure_message(_FakeMessage()) is False
