"""Tests for apps.deepstream.app.ingestion.reconnect."""

from __future__ import annotations

import pytest

from apps.deepstream.app.ingestion.reconnect import ReconnectPolicy, compute_backoff_seconds


class TestComputeBackoffSeconds:
    def test_first_attempt_is_initial_delay(self) -> None:
        assert (
            compute_backoff_seconds(0, initial_seconds=1.0, max_seconds=30.0, multiplier=2.0) == 1.0
        )

    def test_delay_grows_exponentially(self) -> None:
        kwargs = {"initial_seconds": 1.0, "max_seconds": 100.0, "multiplier": 2.0}
        assert compute_backoff_seconds(1, **kwargs) == 2.0
        assert compute_backoff_seconds(2, **kwargs) == 4.0
        assert compute_backoff_seconds(3, **kwargs) == 8.0

    def test_delay_caps_at_max(self) -> None:
        assert (
            compute_backoff_seconds(10, initial_seconds=1.0, max_seconds=30.0, multiplier=2.0)
            == 30.0
        )

    def test_negative_attempt_rejected(self) -> None:
        with pytest.raises(ValueError, match="attempt must be >= 0"):
            compute_backoff_seconds(-1, initial_seconds=1.0, max_seconds=30.0, multiplier=2.0)


class TestReconnectPolicy:
    def test_advances_attempt_count(self) -> None:
        policy = ReconnectPolicy(
            initial_backoff_seconds=1.0, max_backoff_seconds=30.0, multiplier=2.0
        )
        assert policy.attempt_count == 0
        assert policy.next_delay_seconds() == 1.0
        assert policy.attempt_count == 1
        assert policy.next_delay_seconds() == 2.0
        assert policy.attempt_count == 2

    def test_reset_restarts_from_initial_delay(self) -> None:
        policy = ReconnectPolicy(
            initial_backoff_seconds=1.0, max_backoff_seconds=30.0, multiplier=2.0
        )
        policy.next_delay_seconds()
        policy.next_delay_seconds()
        policy.reset()
        assert policy.attempt_count == 0
        assert policy.next_delay_seconds() == 1.0

    def test_independent_instances_do_not_share_state(self) -> None:
        """INV-012: one camera's failure/backoff state must never affect
        another's -- each RtspSource owns its own ReconnectPolicy instance."""
        camera_a = ReconnectPolicy()
        camera_b = ReconnectPolicy()

        camera_a.next_delay_seconds()
        camera_a.next_delay_seconds()
        camera_a.next_delay_seconds()

        assert camera_a.attempt_count == 3
        assert camera_b.attempt_count == 0
