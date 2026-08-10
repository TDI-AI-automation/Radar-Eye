"""Tests for security/auth.py -- RM-12 Phase 1."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import get_settings
from apps.api.app.models.user import ROLE_ADMIN, ROLE_OPERATOR, User
from apps.api.app.security.auth import (
    LocalUserAuthProvider,
    TokenError,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_verify_succeeds_for_the_correct_password(self) -> None:
        password_hash = hash_password("correct horse battery staple")

        assert verify_password("correct horse battery staple", password_hash) is True

    def test_verify_fails_for_the_wrong_password(self) -> None:
        password_hash = hash_password("correct horse battery staple")

        assert verify_password("wrong password", password_hash) is False

    def test_hashing_the_same_password_twice_yields_different_hashes(self) -> None:
        """Randomly salted -- never compare hashes with ==, only via
        verify_password()."""
        first = hash_password("same password")
        second = hash_password("same password")

        assert first != second
        assert verify_password("same password", first) is True
        assert verify_password("same password", second) is True


class TestTokens:
    def test_access_token_decodes_with_the_right_claims(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        user_id = uuid.uuid4()

        tokens = create_token_pair(user_id=user_id, role=ROLE_OPERATOR, settings=settings)
        decoded = decode_token(tokens.access_token, settings=settings, expected_type="access")

        assert decoded.user_id == user_id
        assert decoded.role == ROLE_OPERATOR
        assert decoded.token_type == "access"

    def test_refresh_token_cannot_be_used_as_an_access_token(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_ADMIN, settings=settings)

        with pytest.raises(TokenError):
            decode_token(tokens.access_token, settings=settings, expected_type="refresh")

    def test_access_token_cannot_be_used_as_a_refresh_token(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        tokens = create_token_pair(user_id=uuid.uuid4(), role=ROLE_ADMIN, settings=settings)

        with pytest.raises(TokenError):
            decode_token(tokens.refresh_token, settings=settings, expected_type="access")

    def test_expired_token_is_rejected(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        now = int(time.time())
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "role": ROLE_ADMIN,
            "type": "access",
            "iat": now - 100,
            "exp": now - 1,
        }
        expired_token = jwt.encode(
            expired_payload, settings.auth.jwt_secret.get_secret_value(), algorithm="HS256"
        )

        with pytest.raises(TokenError):
            decode_token(expired_token, settings=settings, expected_type="access")

    def test_token_signed_with_a_different_secret_is_rejected(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        now = int(time.time())
        payload = {
            "sub": str(uuid.uuid4()),
            "role": ROLE_ADMIN,
            "type": "access",
            "iat": now,
            "exp": now + 900,
        }
        forged = jwt.encode(payload, "a-completely-different-secret", algorithm="HS256")

        with pytest.raises(TokenError):
            decode_token(forged, settings=settings, expected_type="access")

    def test_malformed_token_is_rejected(self, _default_env: None) -> None:
        get_settings.cache_clear()
        settings = get_settings()

        with pytest.raises(TokenError):
            decode_token("not-a-real-token", settings=settings, expected_type="access")


class TestLocalUserAuthProvider:
    @pytest.mark.asyncio
    async def test_authenticate_succeeds_for_correct_credentials(
        self, db_session: AsyncSession
    ) -> None:
        user = User(
            username="alice",
            password_hash=hash_password("s3cret-password"),
            role=ROLE_OPERATOR,
        )
        db_session.add(user)
        await db_session.flush()

        provider = LocalUserAuthProvider(db_session)
        result = await provider.authenticate("alice", "s3cret-password")

        assert result is not None
        assert result.user_id == user.id
        assert result.username == "alice"
        assert result.role == ROLE_OPERATOR

    @pytest.mark.asyncio
    async def test_authenticate_fails_for_wrong_password(self, db_session: AsyncSession) -> None:
        user = User(
            username="bob", password_hash=hash_password("correct-password"), role=ROLE_ADMIN
        )
        db_session.add(user)
        await db_session.flush()

        provider = LocalUserAuthProvider(db_session)
        result = await provider.authenticate("bob", "wrong-password")

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_fails_for_unknown_username(self, db_session: AsyncSession) -> None:
        provider = LocalUserAuthProvider(db_session)

        result = await provider.authenticate("nobody", "irrelevant")

        assert result is None
