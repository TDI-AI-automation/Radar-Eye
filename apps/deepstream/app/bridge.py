"""GLib main-loop <-> asyncio bridge.

Source: RM-11 design review, Decision A. DeepStream/GStreamer drives
callbacks (bus messages, pad probes) from its own GLib main-loop thread and
from GStreamer streaming threads -- neither is the application's asyncio
event loop. Every downstream integration point RM-11 must call
(``CalibrationService``, ``ThreatEngine``, ``IncidentService``,
``AlarmService``, ``EventBus``) is ``async def`` and belongs to that asyncio
loop.

``AsyncBridge`` is the single concurrency boundary the design review
approved: it owns a GLib main loop on a dedicated thread and exposes
``schedule()`` -- safe to call from any thread -- to hand a coroutine to the
application's asyncio loop via ``asyncio.run_coroutine_threadsafe``. No other
module should reach across threads on its own.

The real GLib main loop is only imported when ``start()`` actually runs (the
DeepStream/GStreamer SDK is not pip-installable and is absent on non-Jetson
dev machines) -- callers may inject ``mainloop_factory`` to run this bridge's
scheduling logic under test without it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _MainLoop(Protocol):
    def run(self) -> None: ...
    def quit(self) -> None: ...


def _default_mainloop_factory() -> _MainLoop:
    from gi.repository import (
        GLib,  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip
    )

    return GLib.MainLoop()


class BridgeNotRunningError(RuntimeError):
    """schedule() was called before start() or after stop()."""


class AsyncBridge:
    """Runs a GLib main loop on a background thread and bridges it to asyncio."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        mainloop_factory: Callable[[], _MainLoop] = _default_mainloop_factory,
    ) -> None:
        self._loop = loop
        self._mainloop_factory = mainloop_factory
        self._mainloop: _MainLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def mainloop(self) -> _MainLoop:
        """The running GLib main loop -- for attaching bus watches, etc."""
        if self._mainloop is None:
            raise BridgeNotRunningError("AsyncBridge.start() has not been called")
        return self._mainloop

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("AsyncBridge is already started")
        self._mainloop = self._mainloop_factory()
        self._thread = threading.Thread(
            target=self._run, name="deepstream-glib-mainloop", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        assert self._mainloop is not None
        try:
            self._mainloop.run()
        except Exception:
            logger.exception("GLib main loop exited abnormally")

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        if self._mainloop is None or self._thread is None:
            return
        self._mainloop.quit()
        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            logger.warning("GLib main-loop thread did not stop within %ss", timeout_seconds)
        self._mainloop = None
        self._thread = None

    def schedule(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        """Schedule ``coro`` on the application asyncio loop from any thread.

        Safe to call from a GStreamer bus-watch or pad-probe callback. Never
        awaits the result itself -- callers that need the outcome should use
        the returned future's own (thread-safe) ``result()``/callbacks, and
        must not block a GStreamer streaming thread by calling ``.result()``
        synchronously there.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)
