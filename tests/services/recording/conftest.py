"""Recording Service test fixtures."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.models import Base
from services.recording.types import RecordingConfig


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Default environment variables for database settings."""
    monkeypatch.setenv("RADAR_EYE_DB_USER", "test_user")
    monkeypatch.setenv("RADAR_EYE_DB_PASSWORD", "test_password")
    monkeypatch.setenv("RADAR_EYE_ENCRYPTION_KEY", "CLrFKStOGSTRHci9yIv1kJV-SxMwWNDHzUiSWl3C3jA=")
    monkeypatch.setenv(
        "RADAR_EYE_JWT_SECRET", "test-jwt-signing-secret-not-for-production-use-32bytes+"
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine(_default_env: None) -> AsyncIterator[AsyncEngine]:
    """Async engine against PostgreSQL database."""
    settings = get_settings()
    engine = create_engine(settings)

    try:
        async with engine.begin():
            pass
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable, skipping DB-dependent test: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        yield session


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
