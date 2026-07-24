"""FastAPI routers package for apps.api.app."""

from apps.api.app.routers.auth import router as auth_router
from apps.api.app.routers.health import router as health_router

__all__ = ["auth_router", "health_router"]
