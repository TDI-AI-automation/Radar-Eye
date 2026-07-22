"""Tests for apps.deepstream.app.observations.build_frame_observation.

No pyds/Gst dependency -- exercises the pure construction step RuntimeAdapter
hands off to after extracting raw pyds metadata (RM-11 Phase 1).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.deepstream.app.observations import build_frame_observation

_CAMERA = uuid.uuid4()
_INGRESS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_METADATA = datetime(2026, 1, 1, 12, 0, 0, 40000, tzinfo=timezone.utc)


class TestBuildFrameObservation:
    def test_no_detections(self) -> None:
        observation = build_frame_observation(
            camera_id=_CAMERA,
            frame_num=1,
            ingress_timestamp=_INGRESS,
            metadata_timestamp=_METADATA,
            raw_detections=[],
        )

        assert observation.camera_id == _CAMERA
        assert observation.frame_num == 1
        assert observation.ingress_timestamp == _INGRESS
        assert observation.metadata_timestamp == _METADATA
        assert observation.detections == ()

    def test_preserves_wallclock_timestamps_unchanged(self) -> None:
        """Regression guard: these must be passed through as real wall-clock
        datetimes, never reconstructed from a monotonic clock value (which
        has no epoch relationship to wall-clock time)."""
        observation = build_frame_observation(
            camera_id=_CAMERA,
            frame_num=1,
            ingress_timestamp=_INGRESS,
            metadata_timestamp=_METADATA,
            raw_detections=[],
        )

        assert observation.ingress_timestamp is _INGRESS
        assert observation.metadata_timestamp is _METADATA

    def test_detection_with_track_id(self) -> None:
        observation = build_frame_observation(
            camera_id=_CAMERA,
            frame_num=2,
            ingress_timestamp=_INGRESS,
            metadata_timestamp=_METADATA,
            raw_detections=[(3, "car", 0.87, (10.0, 20.0, 30.0, 40.0), 42)],
        )

        assert len(observation.detections) == 1
        detection = observation.detections[0]
        assert detection.class_id == 3
        assert detection.label == "car"
        assert detection.confidence == 0.87
        assert detection.bbox.left == 10.0
        assert detection.bbox.top == 20.0
        assert detection.bbox.width == 30.0
        assert detection.bbox.height == 40.0
        assert detection.track_id == 42

    def test_detection_without_track_id_is_none(self) -> None:
        """Untracked detections (before NvDCF assigns an ID) carry track_id=None."""
        observation = build_frame_observation(
            camera_id=_CAMERA,
            frame_num=3,
            ingress_timestamp=_INGRESS,
            metadata_timestamp=_METADATA,
            raw_detections=[(0, "person", 0.5, (0.0, 0.0, 1.0, 1.0), None)],
        )

        assert observation.detections[0].track_id is None

    def test_multiple_detections_preserve_order(self) -> None:
        raw = [
            (0, "person", 0.9, (0.0, 0.0, 1.0, 1.0), 1),
            (1, "car", 0.8, (1.0, 1.0, 1.0, 1.0), 2),
            (2, "bicycle", 0.7, (2.0, 2.0, 1.0, 1.0), None),
        ]
        observation = build_frame_observation(
            camera_id=_CAMERA,
            frame_num=4,
            ingress_timestamp=_INGRESS,
            metadata_timestamp=_METADATA,
            raw_detections=raw,
        )

        assert [d.label for d in observation.detections] == ["person", "car", "bicycle"]
        assert [d.track_id for d in observation.detections] == [1, 2, None]
