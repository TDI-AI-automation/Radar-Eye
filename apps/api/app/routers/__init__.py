"""FastAPI routers package for apps.api.app."""

from apps.api.app.routers.analytics import router as analytics_router
from apps.api.app.routers.auth import router as auth_router
from apps.api.app.routers.calibration import router as calibration_router
from apps.api.app.routers.cameras import router as cameras_router
from apps.api.app.routers.evidence import router as evidence_router
from apps.api.app.routers.health import router as health_router
from apps.api.app.routers.incidents import router as incidents_router
from apps.api.app.routers.reviews import router as reviews_router
from apps.api.app.routers.threats import router as threats_router
from apps.api.app.routers.users import router as users_router

__all__ = [
    "analytics_router",
    "auth_router",
    "calibration_router",
    "cameras_router",
    "evidence_router",
    "health_router",
    "incidents_router",
    "reviews_router",
    "threats_router",
    "users_router",
]
