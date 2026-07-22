"""DeepStream process entrypoint -- Phase 0 dev/standalone harness.

Not RM-14's final packaging decision. RM-14 (Jetson Deployment & Packaging)
owns how the single required OS process (RM-11 design review, Decision A)
is actually composed and started under systemd -- e.g. whether this module
imports and starts ``apps.api.app.main``'s FastAPI app in-process, or
whether that composition happens the other way around. This entrypoint
exists so Phase 0 has something runnable/testable on real hardware in the
meantime: it builds its own asyncio loop and constructs the shared services
(EventBus, HealthCollector, DB session factory) directly.

Run with:
    python -m apps.deepstream.app.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.health import HealthCollector
from apps.api.app.logging_config import configure_logging
from apps.api.app.security.encryption import get_credential_encryption_provider
from apps.deepstream.app.config import (
    get_logging_settings,
    get_models_settings,
    get_validation_settings,
)
from apps.deepstream.app.config import get_settings as get_deepstream_settings
from apps.deepstream.app.runtime import DeepStreamRuntime
from apps.deepstream.app.stage_logging import configure_stage_logging
from shared.events.bus import InProcessEventBus

logger = logging.getLogger(__name__)


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    configure_stage_logging(get_logging_settings())  # RM-11.SIV -- radar_eye.stage.*/audit levels
    logger.info("radar-eye-deepstream starting", extra={"environment": api_settings.environment})

    deepstream_settings = get_deepstream_settings()
    models_settings = get_models_settings()
    validation_settings = get_validation_settings()
    engine = create_engine(api_settings)
    session_factory = create_session_factory(engine)
    encryption = get_credential_encryption_provider(api_settings)
    bus = InProcessEventBus(source="deepstream")
    health_collector = HealthCollector()

    loop = asyncio.get_running_loop()
    runtime = DeepStreamRuntime(
        loop=loop,
        settings=deepstream_settings,
        models=models_settings,
        validation=validation_settings,
        session_factory=session_factory,
        bus=bus,
        encryption=encryption,
    )
    runtime.set_health_collector(health_collector)

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await runtime.start()
    logger.info("radar-eye-deepstream running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-deepstream shutting down")
        await runtime.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
