"""Recording Service test fixtures.

_default_env, db_engine, db_session are defined once in the repository
root conftest.py -- see that module's docstring for why.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from services.recording.types import RecordingConfig


@pytest.fixture
def temp_storage_dir() -> Iterator[Path]:
    """Temporary directory for recording and snapshot storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def recording_config(temp_storage_dir: Path) -> RecordingConfig:
    """Recording configuration pointing to temporary storage."""
    return RecordingConfig(
        storage_root=str(temp_storage_dir),
        retention_days=30,
        pre_incident_buffer_sec=10,
        post_incident_buffer_sec=20,
        disk_warning_threshold_pct=90.0,
    )
