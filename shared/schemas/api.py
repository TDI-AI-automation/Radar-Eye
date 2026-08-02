"""Standard API response envelope.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — "API Standards" section.

Every REST endpoint returns:
    {"success": true/false, "data": <payload or null>, "error": null}

Usage::

    from shared.schemas.api import ApiResponse
    from shared.schemas.threat import ActiveThreatSchema

    response = ApiResponse[list[ActiveThreatSchema]](
        success=True,
        data=[...],
    )

``error`` (RM-12, docs/RM-12_ARCHITECTURE.md §3.6): additive, defaults to
``None`` -- existing success responses (e.g. every ``health.py`` route)
are unaffected. Populated only on ``success=False`` responses, via
``apps.api.app.main``'s global exception handler -- routers do not build
``ApiError`` themselves.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiError(BaseModel):
    """Structured error detail for a ``success=False`` response.

    ``code`` is a short, stable, machine-readable identifier (e.g.
    ``"not_found"``, ``"invalid_credentials"``, ``"validation_error"``) --
    distinct from the HTTP status code, which the response's own status
    line already carries. ``message`` is human-readable, safe to display,
    never a raw exception string (which could leak internal detail)."""

    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    """Generic wrapper for all REST API responses.

    Matches the mandatory response format in FRONTEND_BACKEND_CONTRACTS.md:
        {"success": true, "data": {}}
    """

    success: bool
    data: T | None = None
    error: ApiError | None = None
