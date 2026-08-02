"""Tests for main.py's global exception handlers -- RM-12 Phase 1
(docs/RM-12_ARCHITECTURE.md §3.6, found missing during the Architecture
Readiness Review). Exercised via throwaway routes added to the real
``create_app()`` instance, since no real route raises each of these on
demand yet.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from apps.api.app.main import create_app


class _Body(BaseModel):
    value: int


def _add_throwaway_routes(app: FastAPI) -> None:
    @app.get("/__test_404")
    async def _not_found() -> None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found")

    @app.get("/__test_401")
    async def _unauthorized() -> None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    @app.post("/__test_validation")
    async def _validation(body: _Body) -> dict[str, int]:
        return {"value": body.value}


@pytest.mark.asyncio
async def test_http_exception_produces_the_documented_error_shape(_default_env: None) -> None:
    app = create_app()
    _add_throwaway_routes(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/__test_404")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] == {"code": "not_found", "message": "Widget not found"}


@pytest.mark.asyncio
async def test_401_maps_to_the_unauthorized_error_code(_default_env: None) -> None:
    app = create_app()
    _add_throwaway_routes(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/__test_401")

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_validation_error_produces_the_documented_error_shape(_default_env: None) -> None:
    app = create_app()
    _add_throwaway_routes(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/__test_validation", json={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_existing_success_responses_are_unaffected(_default_env: None) -> None:
    """The additive `error` field must default to null on every existing
    success response -- health.py's routes are untouched by this phase."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health/gpu")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
