"""Authentication REST router -- RM-12 (docs/RM-12_ARCHITECTURE.md §3.2).

See shared/schemas/auth.py's docstring for why the endpoint paths here are
this module's own choice, not something FRONTEND_BACKEND_CONTRACTS.md
enumerates explicitly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import Settings
from apps.api.app.security.auth import (
    LocalUserAuthProvider,
    TokenError,
    create_token_pair,
    decode_token,
)
from apps.api.app.security.dependencies import get_db_session, get_settings
from shared.schemas.api import ApiResponse
from shared.schemas.auth import LoginRequestSchema, RefreshRequestSchema, TokenResponseSchema

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponseSchema],
    summary="Exchange a username/password for an access + refresh token pair",
)
async def login(
    body: LoginRequestSchema,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> ApiResponse[TokenResponseSchema]:
    if session is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable")

    provider = LocalUserAuthProvider(session)
    user = await provider.authenticate(body.username, body.password)
    if user is None:
        # Deliberately identical whether the username doesn't exist or the
        # password was wrong -- see AuthProvider.authenticate()'s docstring.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    tokens = create_token_pair(user_id=user.user_id, role=user.role, settings=settings)
    return ApiResponse[TokenResponseSchema](
        success=True,
        data=TokenResponseSchema(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        ),
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponseSchema],
    summary="Exchange a refresh token for a new access + refresh token pair",
)
async def refresh(
    body: RefreshRequestSchema,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[TokenResponseSchema]:
    try:
        decoded = decode_token(body.refresh_token, settings=settings, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    tokens = create_token_pair(user_id=decoded.user_id, role=decoded.role, settings=settings)
    return ApiResponse[TokenResponseSchema](
        success=True,
        data=TokenResponseSchema(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        ),
    )
