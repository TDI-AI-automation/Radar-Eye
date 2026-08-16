"""Tests for shared.gst_bridge.AsyncBridge.

Promoted from apps/deepstream/tests/test_bridge.py (Media Architecture
Reset, ADR-028) -- same coverage, new import path. Uses a fake GLib main
loop (threading.Event-backed run()/quit()) injected via mainloop_factory
-- start()/stop() lifecycle and schedule()'s cross-thread contract are
both fully exercised without the real gi/GLib bindings.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

import pytest

from shared.gst_bridge import AsyncBridge, BridgeNotRunningError


class FakeMainLoop:
    """run() blocks until quit() is called -- mirrors GLib.MainLoop's
    contract closely enough to exercise AsyncBridge's thread lifecycle."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self.run_called = threading.Event()
        self.quit_called = threading.Event()

    def run(self) -> None:
        self.run_called.set()
        self._stop.wait(timeout=5)

    def quit(self) -> None:
        self.quit_called.set()
        self._stop.set()


@pytest.mark.asyncio
class TestLifecycle:
    async def test_mainloop_unavailable_before_start(self) -> None:
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop)
        with pytest.raises(BridgeNotRunningError):
            _ = bridge.mainloop

    async def test_start_runs_mainloop_on_background_thread(self) -> None:
        loop = asyncio.get_running_loop()
        fake = FakeMainLoop()
        bridge = AsyncBridge(loop, mainloop_factory=lambda: fake)

        bridge.start()
        assert fake.run_called.wait(timeout=2)
        assert bridge.mainloop is fake

        bridge.stop()
        assert fake.quit_called.is_set()

    async def test_start_twice_raises(self) -> None:
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop)
        bridge.start()
        try:
            with pytest.raises(RuntimeError, match="already started"):
                bridge.start()
        finally:
            bridge.stop()

    async def test_stop_before_start_is_a_no_op(self) -> None:
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop)
        bridge.stop()  # must not raise


@pytest.mark.asyncio
class TestSchedule:
    async def test_schedule_runs_coroutine_on_the_target_loop(self) -> None:
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop)
        ran_on_loop: list[asyncio.AbstractEventLoop] = []

        async def _record() -> None:
            ran_on_loop.append(asyncio.get_running_loop())

        future = bridge.schedule(_record())
        await asyncio.wrap_future(future)

        assert ran_on_loop == [loop]

    async def test_schedule_is_callable_from_a_foreign_thread(self) -> None:
        """The realistic case: a GStreamer bus-watch/pad-probe callback runs
        on a thread that is not the asyncio loop's own thread."""
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop)
        result: list[str] = []
        done = threading.Event()

        async def _record() -> None:
            result.append("scheduled-from-foreign-thread")

        def _foreign_thread_body() -> None:
            future = bridge.schedule(_record())
            future.result(timeout=2)  # safe here: not the loop's own thread
            done.set()

        thread = threading.Thread(target=_foreign_thread_body)
        thread.start()

        # Give the loop a chance to process the scheduled coroutine while
        # this test coroutine is suspended.
        for _ in range(50):
            if done.wait(timeout=0.05):
                break
            await asyncio.sleep(0)
        thread.join(timeout=2)

        assert result == ["scheduled-from-foreign-thread"]


@pytest.mark.asyncio
class TestScheduleOnMainloop:
    async def test_raises_before_start(self) -> None:
        loop = asyncio.get_running_loop()
        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=lambda cb: 0)
        with pytest.raises(BridgeNotRunningError):
            bridge.schedule_on_mainloop(lambda: None)

    async def test_result_is_available_once_the_idle_callback_runs(self) -> None:
        loop = asyncio.get_running_loop()
        captured: list[Callable[[], bool]] = []

        def idle_add(callback: Callable[[], bool]) -> int:
            captured.append(callback)
            return 0

        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=idle_add)
        bridge.start()
        try:
            future = bridge.schedule_on_mainloop(lambda: 42)
            assert not future.done()  # idle_add captured it but hasn't run it

            captured[0]()  # simulate GLib actually running the idle source
            result = await asyncio.wrap_future(future)
            assert result == 42
        finally:
            bridge.stop()

    async def test_exception_in_func_propagates_to_the_future(self) -> None:
        loop = asyncio.get_running_loop()

        def idle_add(callback: Callable[[], bool]) -> int:
            callback()
            return 0

        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=idle_add)
        bridge.start()
        try:

            def _boom() -> None:
                raise ValueError("boom")

            future = bridge.schedule_on_mainloop(_boom)
            with pytest.raises(ValueError, match="boom"):
                await asyncio.wrap_future(future)
        finally:
            bridge.stop()

    async def test_callable_from_a_foreign_thread(self) -> None:
        loop = asyncio.get_running_loop()

        def idle_add(callback: Callable[[], bool]) -> int:
            callback()
            return 0

        bridge = AsyncBridge(loop, mainloop_factory=FakeMainLoop, idle_add=idle_add)
        bridge.start()
        results: list[int] = []
        done = threading.Event()

        def _foreign_thread_body() -> None:
            future = bridge.schedule_on_mainloop(lambda: 7)
            results.append(future.result(timeout=2))
            done.set()

        thread = threading.Thread(target=_foreign_thread_body)
        thread.start()
        for _ in range(50):
            if done.wait(timeout=0.05):
                break
            await asyncio.sleep(0)
        thread.join(timeout=2)
        bridge.stop()

        assert results == [7]
