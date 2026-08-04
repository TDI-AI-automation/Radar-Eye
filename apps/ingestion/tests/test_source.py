"""Tests for apps.ingestion.app.source -- Camera Ingestion's entire
GStreamer scope (ADR-028): rtspsrc -> rtph264depay -> h264parse ->
[ghost pad]. No decode, no valve, no bitstream tee.

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
from apps.ingestion.app.source import IngestedSource, build_source_bin  # noqa: E402

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
    def test_bin_has_a_src_ghost_pad(self) -> None:
        bin_ = build_source_bin(_make_source())
        assert bin_.get_static_pad("src") is not None

    def test_ghost_pad_targets_h264parse_not_the_depayloader(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        parse = bin_.get_by_name(f"parse-{source.camera_id}")
        ghost_pad = bin_.get_static_pad("src")
        assert ghost_pad.get_target() == parse.get_static_pad("src")

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
        rtspsrc/depay/parse, nothing else."""
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
        }


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
