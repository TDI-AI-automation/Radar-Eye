"""Tests for apps.deepstream.app.live_stream.branch's pure-Python helpers.

CameraWebRtcBranch itself (build()/handle_offer()) requires real
NVIDIA-specific GStreamer elements (nvvideoconvert/nvdsosd/
nvv4l2h264enc) tapping a real DeepStreamPipeline's SGIE tee -- hardware-
only, validated on real Jetson hardware (see docs/IMPLEMENTATION_STATUS.md),
not something a generic dev-machine unit test can exercise (unlike the
now-removed shared.media_transport.webrtc.WebRtcBranch, which accepted
any upstream H.264 source and was DeepStream-independent). This file
covers the one piece of branch.py that has no such dependency:
_first_h264_payload_type's plain SDP-text parsing, previously untested
in this module (only a separate, now-removed copy in
shared/media_transport/webrtc.py had coverage, per ADR-030's removal of
that module).
"""

from __future__ import annotations

from apps.deepstream.app.live_stream.branch import _first_h264_payload_type


class TestFirstH264PayloadType:
    def test_extracts_payload_type_from_sdp(self) -> None:
        sdp = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 100\r\na=rtpmap:100 H264/90000\r\n"
        assert _first_h264_payload_type(sdp) == 100

    def test_returns_none_when_no_h264(self) -> None:
        sdp = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=rtpmap:96 VP8/90000\r\n"
        assert _first_h264_payload_type(sdp) is None

    def test_picks_first_of_multiple_h264_payload_types(self) -> None:
        sdp = (
            "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 100 102\r\n"
            "a=rtpmap:100 H264/90000\r\na=rtpmap:102 H264/90000\r\n"
        )
        assert _first_h264_payload_type(sdp) == 100
