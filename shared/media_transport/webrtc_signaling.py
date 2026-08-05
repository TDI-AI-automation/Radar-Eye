"""WebRtcSignalingServer -- the local-only HTTP endpoint a WebRTC-publishing
process (Live Streaming, later AI Streaming) exposes for SDP offer/answer
exchange. Promoted verbatim (renamed, no behavior change) from
``apps/deepstream/app/live_stream/signaling_server.py`` -- already fully
generic, zero DeepStream-specific content.

Bound to ``127.0.0.1`` only, never network-exposed (ADR-011, "centralized
access control" -- ``apps.api`` is the sole externally-reachable
authenticated door; it proxies ``POST /cameras/{camera_id}/webrtc/offer``
here, per ``docs/FRONTEND_BACKEND_CONTRACTS.md``'s WebRTC section).

Non-trickle signaling: a single ``POST /cameras/{camera_id}/webrtc/offer``
request/response is the entire exchange -- the browser waits for its own
ICE gathering to complete before sending the offer, this server waits for
its own before responding with the answer. No persistent connection, no
relay of individual ICE candidates, appropriate for a single-node LAN
deployment with host candidates only.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Protocol

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OfferHandler(Protocol):
    async def handle_offer(self, camera_id: uuid.UUID, sdp_offer_text: str) -> str: ...


class WebRtcOfferRequest(BaseModel):
    sdp: str
    type: str = "offer"


class WebRtcAnswerResponse(BaseModel):
    sdp: str
    type: str = "answer"


def build_app(offer_handler: OfferHandler) -> FastAPI:
    app = FastAPI()

    @app.post("/cameras/{camera_id}/webrtc/offer", response_model=WebRtcAnswerResponse)
    async def post_offer(camera_id: uuid.UUID, body: WebRtcOfferRequest) -> WebRtcAnswerResponse:
        try:
            answer_sdp = await offer_handler.handle_offer(camera_id, body.sdp)
        except KeyError as exc:
            raise HTTPException(404, f"No WebRTC branch for camera {camera_id}") from exc
        except Exception as exc:  # noqa: BLE001 -- surfaced to the operator, not swallowed
            logger.exception("WebRTC offer handling failed for camera %s", camera_id)
            raise HTTPException(500, "Failed to negotiate WebRTC stream") from exc
        return WebRtcAnswerResponse(sdp=answer_sdp)

    return app


class WebRtcSignalingServer:
    """Runs the local-only FastAPI app on its own asyncio task, sharing
    the same event loop as the rest of the owning process (uvicorn's
    ``Server.serve()`` is itself just a coroutine)."""

    def __init__(self, offer_handler: OfferHandler, *, host: str, port: int) -> None:
        self._app = build_app(offer_handler)
        self._host = host
        self._port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app, host=self._host, port=self._port, log_level="warning", loop="asyncio"
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.get_event_loop().create_task(self._server.serve())

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._server = None
        self._task = None
