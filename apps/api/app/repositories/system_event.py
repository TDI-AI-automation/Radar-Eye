from __future__ import annotations

from apps.api.app.models.system_event import SystemEvent
from apps.api.app.repositories.base import Repository


class SystemEventRepository(Repository[SystemEvent]):
    model = SystemEvent
