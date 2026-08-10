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

RM-12 Camera Runtime, Step 3 (Runtime Supervisor) adds the reverse
direction: ``schedule_on_mainloop()`` hands a plain callable from the
asyncio loop (or any thread) onto the GLib main-loop thread via
``GLib.idle_add`` -- the sole mechanism by which Runtime Supervisor mutates
GStreamer pipeline elements (owned by the GLib thread), matching this
module's own "no other module reaches across threads on its own" rule
rather than becoming a second, ad hoc exception to it.

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
from typing import Any, Protocol, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class _MainLoop(Protocol):
    def run(self) -> None: ...
    def quit(self) -> None: ...


def _default_mainloop_factory() -> _MainLoop:
    from gi.repository import (
        GLib,  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip
    )

    return GLib.MainLoop()


def _default_idle_add(callback: Callable[[], bool]) -> int:
    from gi.repository import (
        GLib,  # noqa: PLC0415 -- deferred: provided by the DeepStream/JetPack SDK, not pip
    )

    return GLib.idle_add(callback)


class BridgeNotRunningError(RuntimeError):
    """schedule() was called before start() or after stop()."""


class AsyncBridge:
    """Runs a GLib main loop on a background thread and bridges it to asyncio."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        mainloop_factory: Callable[[], _MainLoop] = _default_mainloop_factory,
        idle_add: Callable[[Callable[[], bool]], int] = _default_idle_add,
    ) -> None:
        self._loop = loop
        self._mainloop_factory = mainloop_factory
        self._idle_add = idle_add
        self._mainloop: _MainLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def mainloop(self) -> _MainLoop:
        """The running GLib main loop -- for attaching bus watches, etc."""
        if self._mainloop is None:
            raise BridgeNotRunningError("AsyncBridge.start() has not been called")
        return self._mainloop

    @property
    def is_running(self) -> bool:
        """RM-12 Camera Runtime Step 5 (Telemetry): a passive, read-only
        readiness check -- true between ``start()`` and ``stop()``. Telemetry
        reads this; nothing about the bridge's own behavior changes because
        of it."""
        return self._mainloop is not None

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

    def schedule_on_mainloop(self, func: Callable[[], T]) -> concurrent.futures.Future[T]:
        """Schedule a zero-arg callable to run on the GLib main-loop thread,
        from any thread (typically the asyncio loop). The reverse of
        ``schedule()`` -- RM-12 Camera Runtime Step 3's sole mechanism for
        mutating GStreamer pipeline elements (owned by the GLib thread) from
        Runtime Supervisor's asyncio-side command handling.

        Returns a ``concurrent.futures.Future`` resolved with ``func``'s
        return value (or exception) once it actually runs on the main loop
        -- callers on the asyncio side should ``await asyncio.wrap_future(...)``
        rather than call ``.result()`` synchronously (that would block the
        loop). Raises ``BridgeNotRunningError`` if called before ``start()``
        or after ``stop()`` -- there is no main loop to schedule onto.
        """
        if self._mainloop is None:
            raise BridgeNotRunningError("AsyncBridge.start() has not been called")

        future: concurrent.futures.Future[T] = concurrent.futures.Future()

        def _invoke() -> bool:
            if not future.set_running_or_notify_cancel():
                return False  # already cancelled by the caller
            try:
                result = func()
            except Exception as exc:  # noqa: BLE001 -- propagated to the future, not swallowed
                future.set_exception(exc)
            else:
                future.set_result(result)
            return False  # GLib.idle_add: False = run once, don't repeat

        self._idle_add(_invoke)
        return future
