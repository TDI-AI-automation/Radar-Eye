"""Audit logging collaborator -- RM-12 Phase 2 (docs/RM-12_ARCHITECTURE.md §3.4).

Constructed once in ``main.py``'s ``create_app()`` and stashed on
``app.state`` (mirrors ``apps.api.app.health.HealthCollector``'s exact
existing pattern). Unlike ``HealthCollector``, an audit write must persist
a row, so ``record()`` takes the calling route's own request-scoped
``AsyncSession`` (the same one already available via
``apps.api.app.security.dependencies.get_db_session``) rather than owning
one itself -- this makes the audit write participate in the same
transaction as the mutation it is recording, so the two can never diverge
(a rolled-back mutation never leaves behind an orphaned audit entry, and a
committed mutation never silently loses its audit trail). ``AuditLogger``
itself holds no state, so one instance is safe to share across concurrent
requests.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.audit_log import AuditLog
from apps.api.app.repositories.audit_log import AuditLogRepository


class AuditLogger:
    """Records a single audited action as an ``audit_log`` row."""

    async def record(
        self,
        session: AsyncSession,
        *,
        actor_user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        return await AuditLogRepository(session).add(entry)
