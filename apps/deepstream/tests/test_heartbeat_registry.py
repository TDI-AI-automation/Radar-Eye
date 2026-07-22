"""Tests for heartbeat_registry.py -- RM-11.SIV Unified Heartbeat requirement:
watchdog and dashboard must read the exact same HeartbeatRegistry."""

from __future__ import annotations

from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry


def test_unknown_component_is_unhealthy_with_zero_counter() -> None:
    registry = HeartbeatRegistry()

    status = registry.status("pgie", stale_after_seconds=5.0)

    assert status.healthy is False
    assert status.counter == 0
    assert status.reason == "no activity recorded yet"


def test_beat_makes_component_healthy_within_threshold() -> None:
    registry = HeartbeatRegistry()

    registry.beat("pgie")
    status = registry.status("pgie", stale_after_seconds=5.0)

    assert status.healthy is True
    assert status.counter == 1


def test_counter_increments_across_multiple_beats() -> None:
    registry = HeartbeatRegistry()

    for _ in range(3):
        registry.beat("sgie")
    status = registry.status("sgie", stale_after_seconds=5.0)

    assert status.counter == 3


def test_stale_component_reports_unhealthy_with_age_in_reason() -> None:
    registry = HeartbeatRegistry()
    registry.beat("tracker")

    # Simulate time passing by asking with an explicit `now` far in the future
    # rather than sleeping -- the registry's status() accepts an injectable
    # clock reading for exactly this reason.
    last_seen = registry.status("tracker", stale_after_seconds=5.0).last_seen_monotonic
    status = registry.status("tracker", stale_after_seconds=5.0, now=last_seen + 10.0)

    assert status.healthy is False
    assert "stale for" in status.reason


def test_reason_is_carried_through_from_beat() -> None:
    registry = HeartbeatRegistry()

    registry.beat("incident", reason="incident_id=abc123")
    status = registry.status("incident", stale_after_seconds=5.0)

    assert status.reason == "incident_id=abc123"


def test_known_components_lists_only_components_that_have_beaten() -> None:
    registry = HeartbeatRegistry()
    registry.beat("pgie")
    registry.beat("sgie")

    assert set(registry.known_components()) == {"pgie", "sgie"}
