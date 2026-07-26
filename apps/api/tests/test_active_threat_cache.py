"""Tests for threats/active_cache.py -- RM-12 Phase 3."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from apps.api.app.threats.active_cache import ActiveThreatCache
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.schemas.threat import ActiveThreatSchema


def _assessment(camera_id: uuid.UUID | None = None, track_id: int = 1) -> ActiveThreatSchema:
    return ActiveThreatSchema(
        camera_id=camera_id or uuid.uuid4(),
        track_id=track_id,
        weapon_type=WeaponType.RANGED_LETHAL,
        uniform=UniformClass.CIVILIAN,
        zone=DistanceZone.ZONE_1,
        threat_level=ThreatLevel.HIGH,
    )


class TestActiveThreatCache:
    def test_empty_cache_returns_no_active_threats(self) -> None:
        cache = ActiveThreatCache()

        assert cache.get_active() == []

    def test_recorded_assessment_is_returned_while_fresh(self) -> None:
        cache = ActiveThreatCache(ttl_seconds=30.0)
        assessment = _assessment()
        now = datetime.now(timezone.utc)

        cache.record(assessment, now=now)

        assert cache.get_active(now=now + timedelta(seconds=5)) == [assessment]

    def test_assessment_expires_after_ttl(self) -> None:
        cache = ActiveThreatCache(ttl_seconds=30.0)
        assessment = _assessment()
        now = datetime.now(timezone.utc)

        cache.record(assessment, now=now)

        assert cache.get_active(now=now + timedelta(seconds=31)) == []

    def test_expired_entries_are_evicted_not_just_hidden(self) -> None:
        cache = ActiveThreatCache(ttl_seconds=30.0)
        assessment = _assessment()
        now = datetime.now(timezone.utc)
        cache.record(assessment, now=now)

        cache.get_active(now=now + timedelta(seconds=31))

        assert cache._entries == {}

    def test_a_new_record_for_the_same_track_replaces_the_old_one(self) -> None:
        cache = ActiveThreatCache()
        camera_id = uuid.uuid4()
        first = _assessment(camera_id=camera_id, track_id=1)
        second = ActiveThreatSchema(
            camera_id=camera_id,
            track_id=1,
            weapon_type=WeaponType.RANGED_LETHAL,
            uniform=UniformClass.MILITARY,
            zone=DistanceZone.ZONE_2,
            threat_level=ThreatLevel.ALLY,
        )

        cache.record(first)
        cache.record(second)

        assert cache.get_active() == [second]

    def test_different_tracks_are_tracked_independently(self) -> None:
        cache = ActiveThreatCache()
        camera_id = uuid.uuid4()
        first = _assessment(camera_id=camera_id, track_id=1)
        second = _assessment(camera_id=camera_id, track_id=2)

        cache.record(first)
        cache.record(second)

        active = cache.get_active()
        assert len(active) == 2
        assert first in active
        assert second in active
