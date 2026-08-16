"""Notification channel extension seam (ADR-029 Phase 6).

Source: docs/ADR_INDEX.md (ADR-029 -- "operator notification (UI/SMS/Email/
WhatsApp -- partially resolves docs/OPEN_QUESTIONS.md Q-005)").

UI delivery needs no implementation here: publishing ``AlertRaisedEvent``
onto the bus *is* the UI channel -- ``apps.api``'s existing WebSocket
bridge relays it to every connected browser on ``/ws/alerts``, the same
pattern every other real-time channel in this repository already uses.
``AlertService`` always includes ``"ui"`` in a raised alert's ``channels``
unconditionally, with no ``NotificationChannel`` needed for it.

SMS/Email/WhatsApp are a different matter: each requires a real external
provider (a carrier gateway, an SMTP relay, the WhatsApp Business API) with
its own credentials/configuration, none of which exists in this air-gapped
deployment (CLAUDE.md's Offline First principle -- internet connectivity is
optional, so an external notification provider can never be assumed
reachable). This module defines the interface those providers would
implement and where they plug in (``AlertService(notification_channels=...)``)
-- matching this repository's established "seam not full implementation"
convention (see e.g. frontend/src/api/instance.ts's ``onUnauthorized``
comment) -- without inventing a specific provider integration nobody has
asked for or can currently test against real hardware/credentials.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.alert_service.service import AlertRecord


class NotificationChannel(ABC):
    """One non-UI delivery mechanism (SMS, Email, WhatsApp, ...)."""

    name: str
    """Short identifier appended to an ``AlertRecord``'s ``channels`` list
    when this channel successfully sends -- e.g. ``"sms"``, ``"email"``."""

    @abstractmethod
    async def send(self, record: AlertRecord) -> bool:
        """Deliver notification of ``record`` via this channel.

        Returns whether delivery succeeded, so callers can decide whether
        to include this channel's ``name`` in the published
        ``AlertRaisedEvent.channels`` list.
        """
