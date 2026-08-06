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
from apps.deepstream.app.config import (
    get_live_stream_settings,
    get_logging_settings,
    get_models_settings,
    get_validation_settings,
    get_visualization_settings,
)
from apps.deepstream.app.config import get_settings as get_deepstream_settings
from apps.deepstream.app.runtime import DeepStreamRuntime
from apps.deepstream.app.siv.dashboard import Dashboard
from apps.deepstream.app.siv.watchdog import Watchdog
from apps.deepstream.app.stage_logging import configure_stage_logging, enable_maximum_observability
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
    visualization_settings = get_visualization_settings()
    live_stream_settings = get_live_stream_settings()

    # Production Validation Mode -- a single config switch
    # (configs/validation.yaml's production_validation_mode.enabled, off
    # by default). Forces the existing per-frame trace on, elevates every
    # radar_eye.stage.* logger to DEBUG, and (below, once the runtime
    # exists) starts the existing RM-11.SIV Dashboard/Watchdog against
    # this real production runtime -- no new metric collection, no
    # behavior change to the pipeline itself. When disabled (the
    # production default), none of this runs.
    if validation_settings.production_validation_mode.enabled:
        validation_settings.frame_trace.enabled = True
        enable_maximum_observability()
        logger.warning(
            "Production Validation Mode ENABLED -- maximum observability active "
            "(per-frame trace, DEBUG stage logging, console dashboard/watchdog). "
            "Set production_validation_mode.enabled: false in configs/validation.yaml "
            "and restart for normal production logging."
        )

    engine = create_engine(api_settings)
    session_factory = create_session_factory(engine)
    bus = InProcessEventBus(source="deepstream")
    health_collector = HealthCollector()

    loop = asyncio.get_running_loop()
    runtime = DeepStreamRuntime(
        loop=loop,
        settings=deepstream_settings,
        models=models_settings,
        validation=validation_settings,
        visualization=visualization_settings,
        live_stream=live_stream_settings,
        session_factory=session_factory,
        bus=bus,
    )
    runtime.set_health_collector(health_collector)

    # Constructed only when Production Validation Mode is on -- reuses
    # runtime.heartbeat_registry/runtime.instrumentation (the exact same
    # objects RuntimeSupervisor/Telemetry/instrumentation already write
    # to) and this process's own EventBus, purely as read-only observers.
    # Dashboard prints to stderr, not stdout (see dashboard.py) so it
    # doesn't fight application logging for the same stream.
    watchdog: Watchdog | None = None
    dashboard_task: asyncio.Task[None] | None = None
    if validation_settings.production_validation_mode.enabled:
        watchdog = Watchdog(
            heartbeat_registry=runtime.heartbeat_registry,
            settings=validation_settings.watchdog,
            bus=bus,
        )
        dashboard = Dashboard(
            heartbeat_registry=runtime.heartbeat_registry,
            instrumentation=runtime.instrumentation,
            settings=validation_settings.watchdog,
        )
        watchdog.start()
        dashboard_task = loop.create_task(
            dashboard.run_forever(
                interval_seconds=validation_settings.production_validation_mode.dashboard_interval_seconds
            )
        )

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await runtime.start()
    logger.info("radar-eye-deepstream running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-deepstream shutting down")
        if dashboard_task is not None:
            dashboard_task.cancel()
        if watchdog is not None:
            watchdog.stop()
        await runtime.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
