"""Tests for security/dependencies.py -- RM-12 Phase 1.

``get_current_user``/``require_role`` have no real protected business
route yet (Phase 1 only adds the intentionally-unprotected ``/auth/*``
routes) -- exercised here against a throwaway route built the same way a
real Phase 3/4 router will use them, per the implementation plan's own
"authenticated test client fixture" + "throwaway test route" language.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from apps.api.app.config import get_settings
from apps.api.app.models.user import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from apps.api.app.security.auth import DecodedToken, create_token_pair
from apps.api.app.security.dependencies import get_current_user, require_role


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(
        user: Annotated[DecodedToken, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"user_id": str(user.user_id), "role": user.role}

    @app.get("/admin-only")
    async def admin_only(
        user: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
    ) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    return app


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_missing_bearer_token_is_rejected_with_401(_default_env: None) -> None:
    app = _build_test_app()
    app.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/whoami")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_bearer_token_is_rejected_with_401(_default_env: None) -> None:
    app = _build_test_app()
    app.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/whoami", headers=_bearer("not-a-real-token"))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_access_token_is_accepted(_default_env: None) -> None:
    app = _build_test_app()
    settings = get_settings()
    app.state.settings = settings
    user_id = uuid.uuid4()
    tokens = create_token_pair(user_id=user_id, role=ROLE_VIEWER, settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/whoami", headers=_bearer(tokens.access_token))

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user_id), "role": ROLE_VIEWER}


@pytest.mark.asyncio
async def test_refresh_token_is_rejected_on_a_route_expecting_an_access_token(
    _default_env: None,
) -> None:
    app = _build_test_app()
    settings = get_settings()
    app.state.settings = settings
    tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_ADMIN, settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/whoami", headers=_bearer(tokens.refresh_token))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_require_role_allows_a_sufficiently_privileged_user(_default_env: None) -> None:
    app = _build_test_app()
    settings = get_settings()
    app.state.settings = settings
    tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_ADMIN, settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/admin-only", headers=_bearer(tokens.access_token))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_require_role_rejects_an_under_privileged_user_with_403(
    _default_env: None,
) -> None:
    app = _build_test_app()
    settings = get_settings()
    app.state.settings = settings
    tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_OPERATOR, settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/admin-only", headers=_bearer(tokens.access_token))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_require_role_rejects_an_unrecognized_role_with_403(_default_env: None) -> None:
    """An unrecognized role must fail closed (rank below everything), not
    open."""
    app = _build_test_app()
    settings = get_settings()
    app.state.settings = settings
    tokens = create_token_pair(user_id=uuid.uuid4(), role="not-a-real-role", settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/admin-only", headers=_bearer(tokens.access_token))

    assert response.status_code == 403
