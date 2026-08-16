"""Tests for apps.deepstream.app.ingestion.source -- RM-12 Camera Runtime
Step 1 (Source Manager: per-source valve integration).

Requires the real DeepStream/GStreamer SDK (gi + nvv4l2decoder + valve) --
skipped, not failed, when unavailable, matching this repo's established
convention for hardware-dependent tests (e.g. db_engine's
skip-if-unreachable). Genuinely exercised on this bench, where the SDK is
present -- see source.py's own module docstring.

Bin *construction* (element creation, linking, ghost pad, valve state)
never requires a reachable camera -- rtspsrc's pad-added callback is the
only part of this module that needs a live stream, and none of these
tests trigger it. That's what makes these real, unmocked, standalone
tests possible without a camera being connected.
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
    # Deliberately not a reachable address -- construction never connects.
    return CameraSource(
        camera_id=camera_id or uuid.uuid4(),
        name="test-camera",
        rtsp_url="rtsp://192.0.2.1:554/does-not-need-to-be-reachable",
        transport="tcp",
    )


class TestValveIntegration:
    def test_valve_element_exists_in_bin(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        assert valve is not None

    def test_valve_is_permanently_open(self) -> None:
        """This milestone: the valve exists but is not yet closeable --
        drop=False always. Toggling is a later milestone's job."""
        source = _make_source()
        bin_ = build_source_bin(source)
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        assert valve.get_property("drop") is False

    def test_ghost_pad_targets_the_valve_not_the_decoder(self) -> None:
        """Element chain: decoder -> valve -> ghost src pad. If the ghost
        pad still targeted the decoder directly, the valve would exist but
        sit off the actual path to nvstreammux -- silently inert."""
        source = _make_source()
        bin_ = build_source_bin(source)
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        ghost_pad = bin_.get_static_pad("src")
        assert ghost_pad.get_target() == valve.get_static_pad("src")

    def test_decoder_links_to_tier1_tee_which_feeds_the_valve(self) -> None:
        """RM-12 Camera Runtime Step 2: decoder -> tee -> valve. The tee is
        the only element inserted between decode and the valve -- the AI
        path's behavior must be unaffected by its presence."""
        source = _make_source()
        bin_ = build_source_bin(source)
        decoder = bin_.get_by_name(f"decoder-{source.camera_id}")
        tee = bin_.get_by_name(tee_element_name(source.camera_id))
        valve = bin_.get_by_name(valve_element_name(source.camera_id))
        decoder_src = decoder.get_static_pad("src")
        assert decoder_src.is_linked()
        assert decoder_src.get_peer() == tee.get_static_pad("sink")

        valve_sink = valve.get_static_pad("sink")
        assert valve_sink.is_linked()
        assert valve_sink.get_peer().get_parent() == tee

    def test_valve_name_is_unique_per_camera(self) -> None:
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        assert valve_element_name(id_a) != valve_element_name(id_b)


class TestRtspJitterbufferLatency:
    """2026-08-16 latency fix: rtspsrc's internal rtpjitterbuffer
    (mode=slave, GStreamer default) grows its buffer without bound on a
    long-lived connection to Camera Ingestion's republished RTSP stream.
    See ``source.py``'s ``build_source_bin`` and
    ``DeepStreamSettings.rtsp_default_latency_ms`` for the full finding."""

    def test_drop_on_latency_is_enabled(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source)
        rtspsrc = bin_.get_by_name(f"rtspsrc-{source.camera_id}")
        assert rtspsrc.get_property("drop-on-latency") is True

    def test_latency_property_uses_the_caller_supplied_value(self) -> None:
        source = _make_source()
        bin_ = build_source_bin(source, latency_ms=1000)
        rtspsrc = bin_.get_by_name(f"rtspsrc-{source.camera_id}")
        assert rtspsrc.get_property("latency") == 1000

    def test_default_latency_is_1000ms(self) -> None:
        """The proven A/B-tested default (200ms dropped ~18-20% of frames
        paired with drop-on-latency; 1000ms measured flat/bounded with no
        frame loss)."""
        source = _make_source()
        bin_ = build_source_bin(source)
        rtspsrc = bin_.get_by_name(f"rtspsrc-{source.camera_id}")
        assert rtspsrc.get_property("latency") == 1000


class TestConstructionDestructionLifecycle:
    def test_bin_reaches_null_state_cleanly(self) -> None:
        """Mirrors pipeline/builder.py's remove_source() teardown -- a bin
        that now includes the valve as a child must still tear down
        cleanly via one set_state(NULL) call on the bin itself (GStreamer
        cascades to children automatically). Nothing about adding one more
        child element should change that."""
        source = _make_source()
        bin_ = build_source_bin(source)
        result = bin_.set_state(Gst.State.NULL)
        assert result != Gst.StateChangeReturn.FAILURE

    def test_repeated_construction_does_not_collide(self) -> None:
        """Multiple distinct cameras' bins (distinct camera_ids -> distinct
        element names, including the valve's) construct and tear down
        independently -- matches add_source()/remove_source() being called
        repeatedly across a real reconnect cycle."""
        sources = [_make_source() for _ in range(3)]
        bins = [build_source_bin(s) for s in sources]
        names = {valve_element_name(s.camera_id) for s in sources}
        assert len(names) == 3  # no collisions
        for bin_ in bins:
            assert bin_.set_state(Gst.State.NULL) != Gst.StateChangeReturn.FAILURE
