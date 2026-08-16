"""Auth request/response schemas -- RM-12.

Endpoint paths (``/auth/login``, ``/auth/refresh``) are
``apps/api/app/routers/auth.py``'s own choice -- FRONTEND_BACKEND_CONTRACTS.md
specifies "Authentication: Session / Token" under its API Standards section
but does not enumerate specific auth endpoint paths, unlike every other
section of that document.
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequestSchema(BaseModel):
    username: str
    password: str


class RefreshRequestSchema(BaseModel):
    refresh_token: str


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
