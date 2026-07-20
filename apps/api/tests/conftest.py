from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.models import Base


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide safe default environment variables for every test.

    Individual tests may still override or remove these via their own
    monkeypatch calls (e.g. to test the missing-credential failure path).
    These also match the local test Postgres container's credentials
    (test_user/test_password@localhost:5432/radar_eye) used by the
    ``db_engine``/``db_session`` fixtures below.
    """
    monkeypatch.setenv("RADAR_EYE_DB_USER", "test_user")
    monkeypatch.setenv("RADAR_EYE_DB_PASSWORD", "test_password")
    monkeypatch.setenv("RADAR_EYE_ENCRYPTION_KEY", "CLrFKStOGSTRHci9yIv1kJV-SxMwWNDHzUiSWl3C3jA=")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine(_default_env: None) -> AsyncIterator[AsyncEngine]:
    """A live async engine against a real PostgreSQL database, with the full
    schema created fresh and torn down per test.

    Per the RM-03 design review's approved testing strategy: SQLite is never
    substituted (production semantics -- JSONB, partial unique indices --
    differ). If PostgreSQL is unreachable (e.g. local/agent-driven dev
    without Docker running), the test is skipped rather than failed; CI
    always has a real PostgreSQL service available.
    """
    settings = get_settings()
    engine = create_engine(settings)

    try:
        async with engine.begin():
            pass
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure means "skip", not "fail"
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
    """An AsyncSession bound to the schema-populated ``db_engine``."""
    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        yield session
