"""WebSocket bridge package for apps.api.app -- RM-12 Phase 5."""

from apps.api.app.websockets.bridge import CHANNELS, WebSocketBridge
from apps.api.app.websockets.connection_manager import ConnectionManager
from apps.api.app.websockets.routes import router as ws_router

__all__ = ["CHANNELS", "ConnectionManager", "WebSocketBridge", "ws_router"]
