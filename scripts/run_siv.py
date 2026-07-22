"""RM-11.SIV entrypoint -- one real camera, watchdog + dashboard running
alongside the production DeepStreamRuntime.

Not a replacement for apps/deepstream/app/main.py, which remains the
production entrypoint (RM-14 decides how it's actually started under
systemd). This is a separate composition root specifically for SIV: the
exact same DeepStreamRuntime/production orchestration main.py starts, plus
the watchdog/dashboard/report tooling this milestone adds. Nothing in
apps/deepstream/app/siv/ is imported by runtime.py itself (see
apps/deepstream/app/siv/__init__.py) -- this script is where that
observation layer actually gets wired on top.

Before running: configs/models.yaml and configs/camera.yaml (via
scripts/siv_register_camera.py) must both be filled in with real values --
see configs/models.yaml's and configs/camera.yaml.example's comments.

Usage:
    python -m scripts.run_siv
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
from apps.deepstream.app.siv.dashboard import Dashboard
from apps.deepstream.app.siv.report import generate_siv_report
from apps.deepstream.app.siv.watchdog import Watchdog
from apps.deepstream.app.stage_logging import configure_stage_logging
from shared.events.bus import InProcessEventBus

logger = logging.getLogger(__name__)

_DASHBOARD_INTERVAL_SECONDS = 2.0


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    configure_stage_logging(get_logging_settings())
    logger.info("RM-11.SIV starting", extra={"environment": api_settings.environment})

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

    watchdog = Watchdog(
        heartbeat_registry=runtime.heartbeat_registry,
        instrumentation=runtime.instrumentation,
        settings=validation_settings.watchdog,
        bus=bus,
    )
    dashboard = Dashboard(
        heartbeat_registry=runtime.heartbeat_registry,
        instrumentation=runtime.instrumentation,
        settings=validation_settings.watchdog,
    )

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await runtime.start()
    watchdog.start()
    dashboard_task = loop.create_task(
        dashboard.run_forever(interval_seconds=_DASHBOARD_INTERVAL_SECONDS)
    )
    logger.info("RM-11.SIV run started -- watchdog and dashboard active")

    try:
        await stop_event.wait()
    finally:
        logger.info("RM-11.SIV run stopping")
        dashboard_task.cancel()
        watchdog.stop()
        await runtime.stop()
        await engine.dispose()

        report_path = generate_siv_report(
            heartbeat_registry=runtime.heartbeat_registry,
            instrumentation=runtime.instrumentation,
            watchdog_settings=validation_settings.watchdog,
        )
        logger.info("SIV report written to %s", report_path)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
