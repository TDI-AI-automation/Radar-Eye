"""Tests for track_annotations.py -- RM-11.SIV visualization subsystem."""

from __future__ import annotations

import uuid

from apps.deepstream.app.visualization.track_annotations import TrackAnnotationRegistry

_CAMERA = uuid.uuid4()


def test_unknown_track_returns_none() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)

    assert registry.get(_CAMERA, 1) is None


def test_update_then_get_returns_recorded_fields() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)

    registry.update(_CAMERA, 1, zone="zone_1", distance_meters=12.3)

    annotation = registry.get(_CAMERA, 1)
    assert annotation is not None
    assert annotation.camera_id == _CAMERA
    assert annotation.track_id == 1
    assert annotation.zone == "zone_1"
    assert annotation.distance_meters == 12.3
    assert annotation.threat_level is None
    assert annotation.rule_id is None


def test_partial_update_does_not_clobber_previously_set_fields() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)

    registry.update(_CAMERA, 1, zone="zone_1", distance_meters=12.3)
    registry.update(_CAMERA, 1, threat_level="HIGH", rule_id="RANGED_LETHAL_ZONE_1")

    annotation = registry.get(_CAMERA, 1)
    assert annotation is not None
    assert annotation.zone == "zone_1"
    assert annotation.distance_meters == 12.3
    assert annotation.threat_level == "HIGH"
    assert annotation.rule_id == "RANGED_LETHAL_ZONE_1"


def test_different_track_ids_on_same_camera_are_independent() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)

    registry.update(_CAMERA, 1, zone="zone_1")
    registry.update(_CAMERA, 2, zone="zone_2")

    assert registry.get(_CAMERA, 1).zone == "zone_1"  # type: ignore[union-attr]
    assert registry.get(_CAMERA, 2).zone == "zone_2"  # type: ignore[union-attr]


def test_different_cameras_with_same_track_id_are_independent() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    other_camera = uuid.uuid4()

    registry.update(_CAMERA, 1, zone="zone_1")
    registry.update(other_camera, 1, zone="zone_3")

    assert registry.get(_CAMERA, 1).zone == "zone_1"  # type: ignore[union-attr]
    assert registry.get(other_camera, 1).zone == "zone_3"  # type: ignore[union-attr]


def test_entry_older_than_ttl_is_treated_as_absent() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    registry.update(_CAMERA, 1, zone="zone_1")

    last_updated = registry.get(_CAMERA, 1).last_updated_monotonic  # type: ignore[union-attr]

    assert registry.get(_CAMERA, 1, now=last_updated + 5.1) is None
    assert registry.get(_CAMERA, 1, now=last_updated + 4.9) is not None


def test_update_sweeps_expired_entries_out_of_the_dict() -> None:
    """The registry must never grow forever -- update() actively evicts
    stale entries from the underlying dict, not just from get()'s view."""
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    registry.update(_CAMERA, 1, zone="zone_1", now=0.0)
    assert registry.size() == 1

    # A second track's update, stamped well past track 1's TTL, must sweep
    # track 1 out of the dict entirely -- not just make it invisible to get().
    registry.update(_CAMERA, 2, zone="zone_2", now=10.0)

    assert registry.size() == 1
    assert registry.get(_CAMERA, 1, now=10.0) is None
    assert registry.get(_CAMERA, 2, now=10.0) is not None


def test_size_counts_all_entries_including_expired_until_next_write() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    registry.update(_CAMERA, 1, zone="zone_1")

    assert registry.size() == 1


def test_active_tracks_excludes_stale_entries() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    registry.update(_CAMERA, 1, zone="zone_1")
    last_updated = registry.get(_CAMERA, 1).last_updated_monotonic  # type: ignore[union-attr]

    assert registry.active_tracks(now=last_updated + 1.0) == [(_CAMERA, 1)]
    assert registry.active_tracks(now=last_updated + 10.0) == []


def test_expired_tracks_lists_only_stale_entries() -> None:
    registry = TrackAnnotationRegistry(ttl_seconds=5.0)
    registry.update(_CAMERA, 1, zone="zone_1")
    last_updated = registry.get(_CAMERA, 1).last_updated_monotonic  # type: ignore[union-attr]

    assert registry.expired_tracks(now=last_updated + 1.0) == []
    assert registry.expired_tracks(now=last_updated + 10.0) == [(_CAMERA, 1)]
