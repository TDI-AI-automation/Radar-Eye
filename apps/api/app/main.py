"""FastAPI application factory.

No application routes are exposed yet -- this milestone only establishes the
app instance, structured logging, and the database engine/session factory.
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

from fastapi import FastAPI

from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

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

    return app
