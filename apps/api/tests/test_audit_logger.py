"""Tests for audit/logger.py -- RM-12 Phase 2."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.models.user import ROLE_OPERATOR, User
from apps.api.app.repositories.audit_log import AuditLogRepository
from apps.api.app.repositories.user import UserRepository


@pytest.mark.asyncio
class TestAuditLogger:
    async def test_record_writes_the_expected_row(self, db_session: AsyncSession) -> None:
        user = await UserRepository(db_session).add(
            User(username="grace", password_hash="not-a-real-hash", role=ROLE_OPERATOR)
        )

        entry = await AuditLogger().record(
            db_session,
            actor_user_id=user.id,
            action="CONFIRM_CIVILIAN",
            resource_type="human_review_item",
            resource_id=str(uuid.uuid4()),
            details={"reason": "visual confirmation"},
        )

        assert entry.id is not None
        fetched = await AuditLogRepository(db_session).get(entry.id)
        assert fetched is not None
        assert fetched.actor_user_id == user.id
        assert fetched.action == "CONFIRM_CIVILIAN"
        assert fetched.details == {"reason": "visual confirmation"}

    async def test_record_defaults_details_to_an_empty_dict(self, db_session: AsyncSession) -> None:
        entry = await AuditLogger().record(
            db_session,
            actor_user_id=None,
            action="AUTO_RESOLVE",
            resource_type="incident",
            resource_id=str(uuid.uuid4()),
        )

        assert entry.details == {}
