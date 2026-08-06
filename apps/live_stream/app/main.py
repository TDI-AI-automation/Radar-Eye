"""Live Streaming Service process entrypoint (ADR-028, Media
Architecture Reset, Phase 2). Standalone -- runs alongside the existing
``apps.deepstream``-owned ``live_stream`` package; not yet the target of
``apps.api``'s WebRTC proxy (see ``apps/live_stream/app/config.py``'s
module docstring for why this uses its own port during this
build-alongside-then-cutover period).

Run with:
    python -m apps.live_stream.app.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.api.app.config import get_settings as get_api_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.logging_config import configure_logging
from apps.live_stream.app.config import get_settings as get_live_streaming_settings
from apps.live_stream.app.runtime import LiveStreamingRuntime

logger = logging.getLogger(__name__)


async def _run() -> None:
    api_settings = get_api_settings()
    configure_logging(api_settings.log_level)
    logger.info(
        "radar-eye-live-streaming starting", extra={"environment": api_settings.environment}
    )

    live_streaming_settings = get_live_streaming_settings()
    engine = create_engine(api_settings)
    session_factory = create_session_factory(engine)

    loop = asyncio.get_running_loop()
    runtime = LiveStreamingRuntime(
        loop=loop, settings=live_streaming_settings, session_factory=session_factory
    )

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await runtime.start()
    logger.info("radar-eye-live-streaming running")
    try:
        await stop_event.wait()
    finally:
        logger.info("radar-eye-live-streaming shutting down")
        await runtime.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
