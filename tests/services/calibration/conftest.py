from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.models import Base
from services.calibration import service as calibration_service


@pytest.fixture(autouse=True)
def _clear_calibration_cache() -> Iterator[None]:
    """CalibrationService's homography cache is module-level/process-wide
    by design (RM-11 Phase 2 design review, Decision A) -- reset it between
    tests so no test observes another's cached state."""
    calibration_service.clear_cache()
    yield
    calibration_service.clear_cache()


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Same defaults as apps/api/tests/conftest.py -- matches the local test
    Postgres container's credentials (test_user/test_password@localhost:5432/radar_eye)."""
    monkeypatch.setenv("RADAR_EYE_DB_USER", "test_user")
    monkeypatch.setenv("RADAR_EYE_DB_PASSWORD", "test_password")
    monkeypatch.setenv("RADAR_EYE_ENCRYPTION_KEY", "CLrFKStOGSTRHci9yIv1kJV-SxMwWNDHzUiSWl3C3jA=")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine(_default_env: None) -> AsyncIterator[AsyncEngine]:
    """A live async engine against a real PostgreSQL database, schema created
    fresh and torn down per test. Skips (not fails) if unreachable -- see
    apps/api/tests/conftest.py for the identical rationale (RM-03 design
    review's testing strategy)."""
    settings = get_settings()
    engine = create_engine(settings)

    try:
        async with engine.begin():
            pass
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure means "skip"
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
