"""Password hashing, JWT issuance/verification, and the local-user auth
provider -- RM-12 (docs/RM-12_ARCHITECTURE.md §3.2).

``AuthProvider`` is an abstract provider interface, mirroring
``security/encryption.py``'s ``CredentialEncryptionProvider`` pattern
exactly: the rest of the application depends only on the abstract
interface, never on ``LocalUserAuthProvider`` directly, so LDAP/AD
(ADR-009's Future State) can be added later as a second concrete
implementation without touching route-level auth dependencies.

Password hashing uses bcrypt (final library choice was explicitly deferred
to implementation by the architecture doc -- bcrypt chosen here: no native
build step beyond the prebuilt wheel, well-established, still an accepted
"modern adaptive hash" per current guidance).
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import bcrypt
import jwt

from apps.api.app.models.user import User
from apps.api.app.repositories.user import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from apps.api.app.config import Settings

_JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return a new, randomly-salted bcrypt hash. Never store the result
    of calling this twice on the same password and expecting equal
    strings -- use ``verify_password`` to compare, never ``==``."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison via bcrypt's own ``checkpw`` -- never
    compare hashes with ``==``."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


@dataclass(frozen=True)
class AuthenticatedUser:
    """What a successful ``AuthProvider.authenticate()`` call returns --
    already reduced to exactly what a token needs, not the ORM ``User``
    itself (callers outside this module should never need to import
    ``apps.api.app.models.user``)."""

    user_id: uuid.UUID
    username: str
    role: str


class AuthProvider(ABC):
    """Authenticates a username/password pair. See module docstring for
    why this is abstract."""

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> AuthenticatedUser | None:
        """Return the authenticated user, or ``None`` for any failure
        (unknown username, wrong password) -- deliberately not
        distinguished, so a caller can never leak "username exists but
        password was wrong" to an attacker via a different response."""


class LocalUserAuthProvider(AuthProvider):
    """Authenticates against this database's own ``users`` table
    (ADR-009's Initial State)."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def authenticate(self, username: str, password: str) -> AuthenticatedUser | None:
        user: User | None = await self._repo.get_by_username(username)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return AuthenticatedUser(user_id=user.id, username=user.username, role=user.role)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class DecodedToken:
    user_id: uuid.UUID
    role: str
    token_type: str
    """``"access"`` or ``"refresh"`` -- callers must check this matches
    what they expected (see ``decode_token``'s ``expected_type``); a
    refresh token must never be accepted where an access token belongs."""


class TokenError(Exception):
    """Any invalid/expired/malformed/wrong-type token. Callers translate
    this into a 401 -- the underlying ``jwt`` library's own exception
    detail is never propagated further than this module, so a caller
    can't accidentally leak internal detail into an HTTP response."""


def create_token_pair(*, user_id: uuid.UUID, role: str, settings: Settings) -> TokenPair:
    now = int(time.time())
    secret = settings.auth.jwt_secret.get_secret_value()

    def _encode(token_type: str, ttl_seconds: int) -> str:
        payload = {
            "sub": str(user_id),
            "role": role,
            "type": token_type,
            "iat": now,
            "exp": now + ttl_seconds,
        }
        return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)

    return TokenPair(
        access_token=_encode("access", settings.auth.access_token_ttl_seconds),
        refresh_token=_encode("refresh", settings.auth.refresh_token_ttl_seconds),
    )


def decode_token(token: str, *, settings: Settings, expected_type: str) -> DecodedToken:
    secret = settings.auth.jwt_secret.get_secret_value()
    try:
        payload = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(f"invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type!r} token")

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("token missing or invalid subject claim") from exc

    role = payload.get("role")
    if not isinstance(role, str):
        raise TokenError("token missing role claim")

    return DecodedToken(user_id=user_id, role=role, token_type=expected_type)
