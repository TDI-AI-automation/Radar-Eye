"""Per-channel WebSocket connection tracking -- RM-12 Phase 5
(docs/RM-12_ARCHITECTURE.md §3.5).

One ``ConnectionManager`` instance is shared by every ``/ws/*`` route and
by ``WebSocketBridge``: routes register/unregister connections as clients
connect/disconnect, the bridge broadcasts translated event payloads to
every connection on a channel. Kept separate from the bridge itself so
"who is currently connected" and "how do bus events get translated and
delivered" are two independent concerns.

No locking: FastAPI/Starlette WebSocket routes and the bridge's bus-event
handlers all run as coroutines on the same single-threaded asyncio event
loop (the same reasoning already established for
``apps.api.app.health.HealthCollector`` and
``apps.api.app.threats.ActiveThreatCache``).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks connected WebSocket clients per channel name."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[channel].add(websocket)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        self._connections[channel].discard(websocket)

    async def broadcast(self, channel: str, message: dict) -> None:
        """Send ``message`` to every currently-connected client on
        ``channel``. A send failure only disconnects that one client --
        never raises, never affects other clients (mirrors
        ``InProcessEventBus``'s per-subscriber fault isolation)."""
        dead: list[WebSocket] = []
        for websocket in list(self._connections[channel]):
            try:
                await websocket.send_json(message)
            except Exception:
                logger.info("Dropping WebSocket client on channel '%s' -- send failed", channel)
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(channel, websocket)
