"""FastAPI auth dependencies -- RM-12 (docs/RM-12_ARCHITECTURE.md §3.2).

``get_current_user``/``require_role`` are the two ``Depends()`` helpers
every future protected route (Phase 3/4) is built against. ``get_db_session``
is also defined here (not auth-specific, but Phase 1 is the first thing
that needs a *shared*, importable version -- ``health.py``'s existing
``_get_db_session`` is private to that module, matching the era before any
other router existed; future phases may relocate this if a better home
becomes obvious, not redone speculatively now).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.config import Settings
from apps.api.app.models.user import ROLE_RANK
from apps.api.app.security.auth import DecodedToken, TokenError, decode_token
from shared.events.bus import EventBus

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a real DB session if ``app.state.db_session_factory`` is
    present, else ``None`` -- mirrors ``health.py``'s ``_get_db_session``
    exactly (same fallback rationale: DB-optional routes degrade
    gracefully rather than hard-failing)."""
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        yield None  # type: ignore[misc]
        return
    async with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_audit_logger(request: Request) -> AuditLogger:
    return request.app.state.audit_logger


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> DecodedToken:
    """Decode and validate the request's bearer access token. Raises 401
    for anything wrong with it -- missing header, malformed, expired,
    wrong-type (a refresh token presented where an access token belongs)
    -- never distinguishing which, so nothing about *why* a token was
    rejected leaks into the response."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(credentials.credentials, settings=settings, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def require_role(minimum_role: str) -> object:
    """Returns a ``Depends()``-able callable rejecting any user whose role
    ranks below ``minimum_role`` (``apps.api.app.models.user.ROLE_RANK`` --
    the proposed, not-yet-ratified taxonomy, kept in that one place so a
    future taxonomy change doesn't need touching every call site of this
    function). An unrecognized role ranks below every known role, never
    above -- fails closed, not open."""

    async def _check(
        user: Annotated[DecodedToken, Depends(get_current_user)],
    ) -> DecodedToken:
        user_rank = ROLE_RANK.get(user.role, -1)
        required_rank = ROLE_RANK.get(minimum_role, 99)
        if user_rank < required_rank:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _check
