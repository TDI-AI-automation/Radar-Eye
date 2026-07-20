from __future__ import annotations

from collections.abc import Iterator

import pytest

from apps.api.app.config import get_settings


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide safe default environment variables for every test.

    Individual tests may still override or remove these via their own
    monkeypatch calls (e.g. to test the missing-credential failure path).
    """
    monkeypatch.setenv("RADAR_EYE_DB_USER", "test_user")
    monkeypatch.setenv("RADAR_EYE_DB_PASSWORD", "test_password")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
