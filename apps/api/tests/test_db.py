from __future__ import annotations

import pytest

from apps.api.app.config import load_settings
from apps.api.app.db import create_engine, create_session_factory


@pytest.mark.asyncio
async def test_engine_and_session_factory_construct_without_connecting() -> None:
    settings = load_settings()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    assert engine is not None
    assert session_factory is not None

    await engine.dispose()


def test_database_url_contains_real_secret_but_repr_masks_it() -> None:
    settings = load_settings()
    secret = settings.database.password.get_secret_value()

    # The connection string must contain the real password -- SQLAlchemy
    # needs it to actually connect.
    assert secret in settings.database_url

    # But the settings object itself must never leak it via repr/str,
    # e.g. if a DatabaseSettings instance ends up in a log line.
    assert secret not in repr(settings.database)
    assert secret not in str(settings.database.password)
