"""FastAPI routers package for apps.api.app."""

from apps.api.app.routers.health import router as health_router

__all__ = ["health_router"]
