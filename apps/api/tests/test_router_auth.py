"""Tests for routers/auth.py -- RM-12 Phase 1.

Router-level (real ``create_app()``, real DB) rather than calling
``LocalUserAuthProvider`` directly -- ``test_security_auth.py`` already
covers that unit. This file proves the actual HTTP contract: status codes,
``ApiResponse`` envelope, and that a seeded user can really log in through
the full stack.

The seeded user must be committed (not just flushed) -- ``create_app()``
opens its own DB engine/connection, separate from the ``db_session``
fixture's, so an uncommitted row on the fixture's own connection would not
be visible to it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from apps.api.app.models.user import ROLE_OPERATOR, User
from apps.api.app.security.auth import hash_password


@pytest.mark.asyncio
async def test_login_succeeds_for_correct_credentials(
    db_engine: object, db_session: AsyncSession, test_settings: Settings
) -> None:
    db_session.add(
        User(
            username="carol",
            password_hash=hash_password("hunter2"),
            role=ROLE_OPERATOR,
        )
    )
    await db_session.commit()

    app = create_app(settings=test_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/auth/login", json={"username": "carol", "password": "hunter2"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]
    assert body["data"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_fails_with_401_for_wrong_password(
    db_engine: object, db_session: AsyncSession, test_settings: Settings
) -> None:
    db_session.add(
        User(username="dave", password_hash=hash_password("correct"), role=ROLE_OPERATOR)
    )
    await db_session.commit()

    app = create_app(settings=test_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/auth/login", json={"username": "dave", "password": "wrong"})

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_login_fails_with_401_for_unknown_username(
    db_engine: object, db_session: AsyncSession, test_settings: Settings
) -> None:
    """Still needs the db_engine/db_session fixtures (unused directly) --
    an "unknown username" answer inherently requires a real DB round-trip
    to determine, and this repo's convention is that any DB-touching test
    skips (not fails) when PostgreSQL is unreachable, matching every other
    DB-dependent test in this suite."""
    app = create_app(settings=test_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/auth/login", json={"username": "nobody", "password": "irrelevant"}
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_a_new_token_pair(
    db_engine: object, db_session: AsyncSession, test_settings: Settings
) -> None:
    db_session.add(User(username="erin", password_hash=hash_password("s3cret"), role=ROLE_OPERATOR))
    await db_session.commit()

    app = create_app(settings=test_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login_response = await client.post(
            "/auth/login", json={"username": "erin", "password": "s3cret"}
        )
        refresh_token = login_response.json()["data"]["refresh_token"]

        refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert refresh_response.status_code == 200
    body = refresh_response.json()
    assert body["success"] is True
    assert "access_token" in body["data"]


@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token_used_as_a_refresh_token(
    db_engine: object, db_session: AsyncSession, test_settings: Settings
) -> None:
    db_session.add(
        User(username="frank", password_hash=hash_password("s3cret"), role=ROLE_OPERATOR)
    )
    await db_session.commit()

    app = create_app(settings=test_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login_response = await client.post(
            "/auth/login", json={"username": "frank", "password": "s3cret"}
        )
        access_token = login_response.json()["data"]["access_token"]

        refresh_response = await client.post("/auth/refresh", json={"refresh_token": access_token})

    assert refresh_response.status_code == 401
