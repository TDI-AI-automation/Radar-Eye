"""FastAPI application factory.

FastAPI's default documentation routes (/docs, /redoc, /openapi.json) are
left enabled.

Run with:
    uvicorn apps.api.app.main:create_app --factory --reload

A factory (rather than a module-level ``app``) is used deliberately so that
importing this module never triggers settings/engine creation as a side
effect -- required environment variables only need to be present when
create_app() is actually called.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.api.app.audit import AuditLogger
from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.health import HealthCollector
from apps.api.app.logging_config import configure_logging
from apps.api.app.routers import (
    analytics_router,
    auth_router,
    calibration_router,
    cameras_router,
    evidence_router,
    health_router,
    incidents_router,
    reviews_router,
    threats_router,
    users_router,
)
from apps.api.app.threats import ActiveThreatCache
from shared.schemas.api import ApiError, ApiResponse

logger = logging.getLogger(__name__)

_ERROR_CODES_BY_STATUS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}
"""Maps an HTTP status code to a short, stable, machine-readable
ApiError.code (docs/RM-12_ARCHITECTURE.md §3.6) -- the status line already
carries the numeric code; this is for programmatic branching on the
frontend without parsing ``message`` strings. Falls back to "error" for
anything not listed here (see the handlers below)."""


def _error_response(status_code: int, message: str) -> JSONResponse:
    code = _ERROR_CODES_BY_STATUS.get(status_code, "error")
    body = ApiResponse[None](success=False, data=None, error=ApiError(code=code, message=message))
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    health_collector = HealthCollector()
    audit_logger = AuditLogger()
    active_threat_cache = ActiveThreatCache()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "radar-eye-api starting",
            extra={"environment": settings.environment},
        )
        yield
        await engine.dispose()
        logger.info("radar-eye-api shutting down")

    app = FastAPI(title="Radar Eye API", lifespan=lifespan)

    app.state.settings = settings
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    app.state.health_collector = health_collector
    app.state.audit_logger = audit_logger
    app.state.active_threat_cache = active_threat_cache

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return _error_response(exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(cameras_router)
    app.include_router(threats_router)
    app.include_router(incidents_router)
    app.include_router(reviews_router)
    app.include_router(calibration_router)
    app.include_router(evidence_router)
    app.include_router(analytics_router)
    app.include_router(users_router)

    return app
