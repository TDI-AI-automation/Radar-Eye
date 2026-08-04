"""Camera Ingestion Service process entrypoint (ADR-028, Media
Architecture Reset, Phase 1). Standalone -- runs alongside the existing
``apps.deepstream``-owned ingestion path, wired to zero consumers.

Run with:
    python -m apps.ingestion.app.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.logging_config import configure_logging
from apps.ingestion.app.config import get_settings as get_ingestion_settings
from apps.ingestion.app.runtime import IngestionRuntime

logger = logging.getLogger(__name__)


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    logger.info("radar-eye-ingestion starting", extra={"environment": api_settings.environment})

    ingestion_settings = get_ingestion_settings()
    engine = create_engine(api_settings)
    session_factory = create_session_factory(engine)

    loop = asyncio.get_running_loop()
    runtime = IngestionRuntime(
        loop=loop, settings=ingestion_settings, session_factory=session_factory
    )

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await runtime.start()
    logger.info("radar-eye-ingestion running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-ingestion shutting down")
        await runtime.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
