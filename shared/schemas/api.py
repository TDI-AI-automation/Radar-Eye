"""Standard API response envelope.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — "API Standards" section.

Every REST endpoint returns:
    {"success": true/false, "data": <payload or null>}

Usage::

    from shared.schemas.api import ApiResponse
    from shared.schemas.threat import ActiveThreatSchema

    response = ApiResponse[list[ActiveThreatSchema]](
        success=True,
        data=[...],
    )
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic wrapper for all REST API responses.

    Matches the mandatory response format in FRONTEND_BACKEND_CONTRACTS.md:
        {"success": true, "data": {}}
    """

    success: bool
    data: T | None = None
