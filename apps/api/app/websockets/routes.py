"""WebSocket route registrations -- RM-12 Phase 5.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Real-Time Event Streams.
  - /ws/threats
  - /ws/incidents
  - /ws/camera-health
  - /ws/reviews
  - /ws/alarms

``/ws/tracking`` is not implemented (docs/OPEN_QUESTIONS.md Q-015).

**Authentication**: browsers' native WebSocket API cannot set an
``Authorization`` header on the handshake request, so (unlike every REST
route) the access token is passed as a ``?token=`` query parameter,
validated with the same ``decode_token()`` Phase 1 already built. Missing
or invalid tokens close the connection with code 1008 (policy violation)
before ``ConnectionManager.connect()`` ever accepts it.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from apps.api.app.config import Settings
from apps.api.app.security.auth import TokenError, decode_token
from apps.api.app.websockets.connection_manager import ConnectionManager

router = APIRouter(tags=["Real-Time Event Streams"])

_POLICY_VIOLATION = status.WS_1008_POLICY_VIOLATION


def _get_connection_manager(websocket: WebSocket) -> ConnectionManager:
    manager: ConnectionManager | None = getattr(websocket.app.state, "ws_connection_manager", None)
    if manager is None:
        manager = ConnectionManager()
        websocket.app.state.ws_connection_manager = manager
    return manager


async def _authenticate(websocket: WebSocket) -> bool:
    """Validates the ``?token=`` query parameter. Closes and returns False
    on any failure; the caller must not call ``connect()`` afterward."""
    settings: Settings = websocket.app.state.settings
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(code=_POLICY_VIOLATION, reason="Missing token")
        return False
    try:
        decode_token(token, settings=settings, expected_type="access")
    except TokenError:
        await websocket.close(code=_POLICY_VIOLATION, reason="Invalid token")
        return False
    return True


async def _run_channel(websocket: WebSocket, channel: str) -> None:
    if not await _authenticate(websocket):
        return

    manager = _get_connection_manager(websocket)
    await manager.connect(channel, websocket)
    try:
        while True:
            # This channel is broadcast-only (server -> client); incoming
            # messages are not part of any documented contract. Waiting on
            # receive() is only how a FastAPI WebSocket route observes the
            # client disconnecting.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(channel, websocket)


@router.websocket("/ws/threats")
async def ws_threats(websocket: WebSocket) -> None:
    await _run_channel(websocket, "threats")


@router.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket) -> None:
    await _run_channel(websocket, "incidents")


@router.websocket("/ws/camera-health")
async def ws_camera_health(websocket: WebSocket) -> None:
    await _run_channel(websocket, "camera_health")


@router.websocket("/ws/reviews")
async def ws_reviews(websocket: WebSocket) -> None:
    await _run_channel(websocket, "reviews")


@router.websocket("/ws/alarms")
async def ws_alarms(websocket: WebSocket) -> None:
    await _run_channel(websocket, "alarms")
