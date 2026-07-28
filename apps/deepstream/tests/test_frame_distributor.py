"""Tests for apps.deepstream.app.pipeline.frame_distributor -- RM-12 Camera
Runtime Step 2 (Frame Distributor: per-camera Tier 1 tee + raw-stub
terminator).

Same real-hardware, unmocked convention as test_source.py -- skipped, not
failed, when the DeepStream/GStreamer SDK is unavailable. Construction-only:
none of these tests require a reachable camera.
"""

from __future__ import annotations

import uuid

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from apps.deepstream.app.ingestion.camera_registry import CameraSource  # noqa: E402
from apps.deepstream.app.ingestion.source import build_source_bin, valve_element_name  # noqa: E402
from apps.deepstream.app.pipeline.frame_distributor import tee_element_name  # noqa: E402

Gst.init(None)


def _missing_plugins() -> list[str]:
    return [
        name
        for name in (
            "rtspsrc",
            "rtph264depay",
            "h264parse",
            "nvv4l2decoder",
            "valve",
            "tee",
            "queue",
            "fakesink",
        )
        if Gst.ElementFactory.find(name) is None
    ]


@pytest.fixture(autouse=True)
def _require_deepstream_plugins() -> None:
    missing = _missing_plugins()
    if missing:
        pytest.skip(f"GStreamer/DeepStream plugin(s) not installed on this machine: {missing}")


def _make_source(camera_id: uuid.UUID | None = None) -> CameraSource:
    return CameraSource(
        camera_id=camera_id or uuid.uuid4(),
        name="test-camera",
        rtsp_url="rtsp://192.0.2.1:554/does-not-need-to-be-reachable",
        transport="tcp",
    )


class TestTier1TeeIntegration:
    def test_tee_element_exists_in_bin(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        assert tee is not None

    def test_tee_has_exactly_two_src_pads(self) -> None:
        """One request pad for the raw-stub branch, one for the AI/valve
        branch -- no third branch exists at this milestone."""
        source = _make_source()
        bin_ = build_source_bin(source)
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        assert tee.numsrcpads == 2

    def test_tee_name_is_unique_per_camera(self) -> None:
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        assert tee_element_name(id_a) != tee_element_name(id_b)


class TestRawStubBranch:
    def test_raw_queue_and_sink_exist(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        queue = bin_.get_by_name(f"tier1-raw-queue-{source.camera_id}")
        sink = bin_.get_by_name(f"tier1-raw-sink-{source.camera_id}")
        assert queue is not None
        assert sink is not None

    def test_raw_queue_is_leaky_and_bounded(self) -> None:
        """Mirrors visualization/pipeline_builder.py's proven viz-queue
        shape: leaky=2 (downstream: drop oldest), bounded purely by buffer
        count -- never blocks the tee, so the raw branch can never apply
        backpressure back through the tee onto the AI branch."""
        source = _make_source()
        bin_ = build_source_bin(source)
        queue = bin_.get_by_name(f"tier1-raw-queue-{source.camera_id}")
        assert queue.get_property("leaky") == 2
        assert queue.get_property("max-size-buffers") == 4
        assert queue.get_property("max-size-bytes") == 0
        assert queue.get_property("max-size-time") == 0

    def test_raw_sink_never_synchronizes_or_blocks(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        sink = bin_.get_by_name(f"tier1-raw-sink-{source.camera_id}")
        assert sink.get_property("sync") is False
        assert sink.get_property("async") is False

    def test_raw_branch_is_fully_linked_from_the_tee(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        queue = bin_.get_by_name(f"tier1-raw-queue-{source.camera_id}")
        sink = bin_.get_by_name(f"tier1-raw-sink-{source.camera_id}")

        queue_sink_pad = queue.get_static_pad("sink")
        assert queue_sink_pad.is_linked()
        assert queue_sink_pad.get_peer().get_parent() == tee

        queue_src_pad = queue.get_static_pad("src")
        assert queue_src_pad.is_linked()
        assert queue_src_pad.get_peer() == sink.get_static_pad("sink")


class TestAiPathUnaffected:
    """The whole point of positioning the tee before the valve: the AI path
    must be structurally identical to Step 1's decoder -> valve -> ghost pad
    chain, just with the tee as an intermediate hop."""

    def test_valve_still_permanently_open(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        assert valve.get_property("drop") is False

    def test_ghost_pad_still_targets_the_valve(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        ghost_pad = bin_.get_static_pad("src")
        assert ghost_pad.get_target() == valve.get_static_pad("src")


class TestConstructionDestructionLifecycle:
    def test_bin_reaches_null_state_cleanly_with_tee_present(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        result = bin_.set_state(Gst.State.NULL)
        assert result != Gst.StateChangeReturn.FAILURE

    def test_repeated_construction_does_not_collide(self) -> None:
        sources = [_make_source() for _ in range(3)]
        bins = [build_source_bin(s) for s in sources]
        tee_names = {tee_element_name(s.camera_id) for s in sources}
        assert len(tee_names) == 3
        for bin_ in bins:
            assert bin_.set_state(Gst.State.NULL) != Gst.StateChangeReturn.FAILURE
