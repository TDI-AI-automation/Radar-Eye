from __future__ import annotations

from apps.api.app.models.audit_log import AuditLog
from apps.api.app.repositories.base import Repository


class AuditLogRepository(Repository[AuditLog]):
    model = AuditLog
