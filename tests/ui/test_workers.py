from __future__ import annotations

import asyncio

from placement_optimizer.ui.workers import AsyncOperationWorker


def test_async_operation_worker_cancels_active_network_style_task(qtbot) -> None:
    started = False
    cancelled = []

    async def operation(_worker):
        nonlocal started
        started = True
        await asyncio.Event().wait()

    worker = AsyncOperationWorker(operation)
    worker.cancelled_operation.connect(lambda: cancelled.append(True))
    worker.start()
    qtbot.waitUntil(lambda: started, timeout=2000)

    worker.cancel()

    qtbot.waitUntil(lambda: bool(cancelled) and not worker.isRunning(), timeout=2000)
    assert cancelled == [True]
    worker.deleteLater()
