from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.app.db import create_session_factory

# _default_env, db_engine, db_session are defined once in the repository
# root conftest.py -- see that module's docstring for why.


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A session *factory* (as opposed to db_session's single open session)
    -- for tests whose subject opens its own short-lived sessions per call
    rather than holding one open session for the test's duration."""
    return create_session_factory(db_engine)
