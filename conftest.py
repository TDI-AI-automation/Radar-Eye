"""Root conftest.py — sys.path bootstrap, plus the one and only
DB-fixture implementation for the whole repository.

This makes ``shared``, ``apps``, and ``services`` importable from any test
subtree without requiring editable installs.  Developer tooling (RM-DEV)
will formalise the packaging approach; for now this matches the import
pattern established by RM-01.

``_default_env``/``db_engine``/``db_session`` used to be duplicated,
nearly verbatim, across six separate ``conftest.py`` files. That
duplication is exactly what let a real incident happen twice: every copy
derived its connection string from ``apps.api.app.config.get_settings()``
-- the *same* database the real, persistent development stack uses --
distinguished only by which credentials were active, never by database
name. A ``test_user`` role that happened to already exist in that same
persistent database was enough to make the connection succeed, so
``db_engine``'s teardown (``Base.metadata.drop_all()``) ran directly
against real application data. Twice.

A third, independent occurrence: ``apps/api/tests/test_migrations.py``
never used ``db_engine``/``db_session`` at all -- it called
``get_settings()`` directly and ran raw ``DROP TABLE ... CASCADE`` plus
``alembic downgrade base`` against it. A fourth: ``create_app()`` itself
(and the two operator scripts, ``scripts/show_registered_cameras.py``/
``scripts/siv_register_camera.py``) always called the module-level
``get_settings()`` internally with no way to inject a different one, so
any test exercising them (most of ``apps/api/tests/test_routers_*.py``,
``test_router_auth.py``, ``test_health.py``, and both scripts' own
tests) silently read and wrote real ``radar_eye`` data even after the
first fix above. A grep for the *method names* ``Base.metadata.
drop_all``/``create_all`` alone does not catch either of these -- any
code path that resolves a database from ``get_settings()`` rather than
``RADAR_EYE_TEST_DATABASE_URL`` is capable of the same failure,
regardless of which specific statement touches it.

Fixed architecturally, not with monkeypatching: ``create_app()``,
``show_registered_cameras()``, and ``register_camera()`` each now take
an optional ``settings: Settings | None = None`` parameter, defaulting
to ``get_settings()`` only when the caller omits it -- production calls
them with no argument (identical behavior); tests pass ``test_settings``
(below) explicitly. Alembic's own ``env.py`` only calls ``get_settings()``
if nothing already set ``sqlalchemy.url`` on its ``Config``, so
``test_migrations.py`` sets that URL directly instead of needing
``get_settings()`` redirected at all. ``test_settings`` is a plain
object construction -- no ``monkeypatch.setattr`` anywhere in this
file anymore.

Fixed here, once, for the whole repository:
  - DB-dependent tests now require ``RADAR_EYE_TEST_DATABASE_URL`` --
    a connection string set up front, independent of
    ``apps.api.app.config.get_settings()`` entirely. If it isn't set,
    the test session fails immediately (``pytest.fail``, not skip) --
    a missing test database is a broken test environment, not something
    to silently route around.
  - ``_assert_is_test_database`` refuses to proceed unless the resolved
    database *name* itself ends in ``_test`` -- independent of how the
    URL was obtained, so a copy-paste mistake pointing the variable at a
    real database is still caught, not just a trust-the-env-var check.
  - Every other ``conftest.py`` that used to duplicate this now inherits
    it from here instead -- there is exactly one place left to get this
    right.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# Insert the repository root as the first entry so project packages take
# precedence over any same-named installed packages. Must run before any
# `apps`/`shared`/`services` import below -- this repo has no editable
# install, so nothing else makes those packages importable.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

TEST_DATABASE_URL_ENV_VAR = "RADAR_EYE_TEST_DATABASE_URL"


def _assert_is_test_database(url: str) -> None:
    """Refuses to proceed unless the database name unambiguously marks
    itself as disposable test data. Deliberately independent of *how*
    the URL was obtained -- this is the last line of defense, not the
    only one."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.fail(
            f"Refusing to run destructive DB operations against database {name!r} -- "
            f"its name does not end in '_test'. {TEST_DATABASE_URL_ENV_VAR} must point at "
            "a dedicated, disposable database, never the real development/production one.",
            pytrace=False,
        )


def _require_test_database_url() -> str:
    url = os.environ.get(TEST_DATABASE_URL_ENV_VAR)
    if not url:
        pytest.fail(
            f"{TEST_DATABASE_URL_ENV_VAR} is not set. DB-dependent tests require an "
            "explicit, dedicated test database -- they never fall back to "
            "apps.api.app.config.get_settings() (that is always the real development/"
            "production database). Set it to a database whose name ends in '_test', "
            "e.g. postgresql+asyncpg://user:pass@localhost:5432/radar_eye_test -- "
            "see .env.example.",
            pytrace=False,
        )
    _assert_is_test_database(url)
    return url


@pytest.fixture
def test_database_url() -> str:
    """The guarded test database URL, for any test that needs to build its
    own engine/connection directly rather than using ``db_engine``/
    ``db_session`` -- still goes through the same required-env-var +
    name-must-end-in-``_test`` guard, never ``get_settings()``."""
    return _require_test_database_url()


@pytest.fixture
def test_settings(test_database_url: str, _default_env: None):
    """A real ``Settings`` object whose ``database`` points at the guarded
    test database -- built directly, once, and handed to whichever
    composition root needs it (``create_app(settings=test_settings)``,
    ``show_registered_cameras(settings=test_settings)``,
    ``register_camera(..., settings=test_settings)``). No global state is
    mutated: each caller receives this object as an explicit argument, and
    ``apps.api.app.config.get_settings()`` itself is never touched or
    monkeypatched. ``RADAR_EYE_TEST_DATABASE_URL`` (via
    ``test_database_url``) remains the one source of truth for what the
    test database is; this is just that same value reshaped into a full
    ``Settings`` object for callers that need one."""
    from pydantic import SecretStr
    from sqlalchemy.engine import make_url

    from apps.api.app.config import get_settings

    parsed = make_url(test_database_url)
    real_settings = get_settings()  # non-DB fields only: auth, cors, etc.
    return real_settings.model_copy(
        update={
            "database": real_settings.database.model_copy(
                update={
                    "host": parsed.host,
                    "port": parsed.port,
                    "name": parsed.database,
                    "user": parsed.username,
                    "password": SecretStr(parsed.password or ""),
                }
            )
        }
    )


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Safe default environment variables every test gets, for the
    settings ``apps.api.app.config.get_settings()`` itself requires
    (encryption/JWT secrets) -- unrelated to, and never used for, the
    DB-fixture connection below. Individual tests may still override or
    remove these via their own monkeypatch calls."""
    from apps.api.app.config import get_settings

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
    """A live async engine against the dedicated test database (never the
    real one -- see ``_require_test_database_url``), schema created fresh
    and torn down per test. Skips (not fails) only on a *connectivity*
    failure against an already-validated test database (e.g. no Docker
    running locally) -- CI always has one available."""
    from apps.api.app.models import Base

    test_database_url = _require_test_database_url()
    engine = create_async_engine(test_database_url, future=True)

    try:
        async with engine.begin():
            pass
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure means "skip"
        await engine.dispose()
        pytest.skip(f"Test PostgreSQL database is not reachable, skipping: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    from apps.api.app.db import create_session_factory

    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        yield session
