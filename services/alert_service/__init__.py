"""Alert Service -- alert generation, severity, deduplication, operator
notification, and HIGH/FIRE alarm-eligibility (ADR-029 Phase 6).

Source: docs/ADR_INDEX.md (ADR-029). Authority: ADR-012, ADR-026, ADR-029.
"""

from __future__ import annotations

from services.alert_service.alarm import (
    AlarmAdapter,
    AlarmRecord,
    AlarmService,
    AlarmState,
    AlarmTargetType,
    MockAlarmAdapter,
)
from services.alert_service.notification import NotificationChannel
from services.alert_service.service import AlertRecord, AlertService, AlertState

__all__ = [
    "AlarmAdapter",
    "AlarmRecord",
    "AlarmService",
    "AlarmState",
    "AlarmTargetType",
    "AlertRecord",
    "AlertService",
    "AlertState",
    "MockAlarmAdapter",
    "NotificationChannel",
]
