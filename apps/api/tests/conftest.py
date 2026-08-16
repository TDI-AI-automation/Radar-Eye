from __future__ import annotations

import uuid

import pytest

from apps.api.app.config import get_settings
from apps.api.app.models.user import ROLE_ADMIN
from apps.api.app.security.auth import create_token_pair

# _default_env, db_engine, db_session are defined once in the repository
# root conftest.py -- see that module's docstring for why.


@pytest.fixture
def auth_header(_default_env: None) -> dict[str, str]:
    """A ready-to-use ``Authorization`` header for an admin-role user,
    against a freshly-issued access token -- for any test that needs a
    valid, authenticated request without exercising the login flow itself
    (which has its own dedicated tests). No DB round-trip -- JWTs are
    stateless, so this only needs ``get_settings()`` to sign with the same
    secret the app under test will verify with."""
    settings = get_settings()
    tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_ADMIN, settings=settings)
    return {"Authorization": f"Bearer {tokens.access_token}"}
