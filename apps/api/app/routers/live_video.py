"""Live Video WebSocket relay -- Live Monitoring's video delivery
(ADR-032).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Live Monitoring / Live Video
  section.
  - WS /ws/cameras/{camera_id}/video

apps.deepstream's ``hlssink2``-successor branch (``apps/deepstream/app/
live_stream/branch.py``) writes low-latency MPEG-TS to a persistent,
loopback-only ``tcpserversink`` -- one fixed TCP port per camera,
discovered here via ``camera_media_endpoints`` (``subsystem="live_stream"``,
the same DB-backed service-discovery pattern ``apps.ingestion`` already
uses for its own RTSP republish endpoint). This route is a pure byte
relay: one WebSocket connection opens one dedicated TCP connection to
that port and forwards bytes verbatim, in both directions independently
-- ``tcpserversink`` itself is what makes any number of simultaneous
browser connections possible without DeepStream's pipeline ever being
touched; this route holds no shared/broadcast state of its own.

**Authentication**: same as every other WebSocket channel in this
service (``apps/api/app/websockets/routes.py``) -- browsers' native
WebSocket API cannot set an ``Authorization`` header on the handshake
request, so the access token is passed as a ``?token=`` query parameter.
Missing or invalid tokens close the connection with code 1008 (policy
violation) before any TCP connection to DeepStream is attempted.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from apps.api.app.config import Settings
from apps.api.app.repositories.media import CameraMediaEndpointRepository
from apps.api.app.security.auth import TokenError, decode_token

router = APIRouter(tags=["Live Video"])

_POLICY_VIOLATION = status.WS_1008_POLICY_VIOLATION
_SUBSYSTEM = "live_stream"
_CHUNK_SIZE = 65536


async def _authenticate(websocket: WebSocket) -> bool:
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


@router.websocket("/ws/cameras/{camera_id}/video")
async def ws_camera_video(websocket: WebSocket, camera_id: uuid.UUID) -> None:
    if not await _authenticate(websocket):
        return

    session_factory = getattr(websocket.app.state, "db_session_factory", None)
    if session_factory is None:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Database unavailable")
        return

    async with session_factory() as session:
        endpoint = await CameraMediaEndpointRepository(session).get_by_camera_and_subsystem(
            camera_id, _SUBSYSTEM
        )
    if endpoint is None:
        # Camera not added to Live Monitoring yet (matches VideoProvider's
        # "unavailable" status, not a server error) -- 1013 ("try again
        # later") rather than 1011, so the frontend's retry behavior
        # treats this the same way it already treats a not-yet-ready HLS
        # playlist/RTSP endpoint elsewhere in this codebase.
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Camera not streaming")
        return

    host, _, port_text = endpoint.address.rpartition(":")
    try:
        port = int(port_text)
    except ValueError:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Invalid endpoint")
        return

    await websocket.accept()

    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Video source unavailable")
        return

    try:
        while True:
            chunk = await reader.read(_CHUNK_SIZE)
            if not chunk:
                break
            await websocket.send_bytes(chunk)
    except WebSocketDisconnect:
        pass
    finally:
        writer.close()
