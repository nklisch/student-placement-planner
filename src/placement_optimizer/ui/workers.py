"""Off-thread placement calculation with safe cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from threading import Event, Lock

from PySide6.QtCore import QObject, QThread, Signal

from placement_optimizer.application import (
    OutcomeKind,
    PlacementProject,
    SolveProjectOutcome,
    solve_project,
)
from placement_optimizer.optimization import OptimizationCancellation
from placement_optimizer.travel import (
    MapPackDownloadCancelled,
    MapPackError,
    TravelDataError,
)

AsyncTask = Callable[["AsyncOperationWorker"], Awaitable[object]]


class AsyncOperationWorker(QThread):
    """Run one cancellable provider or pack operation on its own event loop."""

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled_operation = Signal()
    # Qt's `int` signal type is signed 32-bit; regional map extracts can be
    # larger than 2 GB, so preserve byte counts as Python integers.
    progress = Signal(object, object, str)

    def __init__(self, task: AsyncTask, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._task_factory = task
        self._cancel_requested = Event()
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    @property
    def is_cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def report_progress(self, completed: int, total: int, message: str = "") -> None:
        self.progress.emit(completed, total, message)

    def cancel(self) -> None:
        self._cancel_requested.set()
        with self._lock:
            loop = self._loop
            task = self._task
        if loop is not None and task is not None:
            # Completion can close the loop between taking the lock and
            # scheduling cancellation. The requested flag still wins.
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(task.cancel)

    def run(self) -> None:
        try:
            asyncio.run(self._execute())
        except Exception:
            # Also cover task-factory/event-loop setup failures. Never expose
            # arbitrary exception text, which can contain provider credentials.
            self.failed.emit("That operation couldn't be completed. Try again or use another mode.")

    async def _execute(self) -> None:
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(self._task_factory(self))
        with self._lock:
            self._loop = loop
            self._task = task
        if self._cancel_requested.is_set():
            task.cancel()
        try:
            result = await task
        except (asyncio.CancelledError, MapPackDownloadCancelled):
            self.cancelled_operation.emit()
        except (MapPackError, TravelDataError) as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("That operation couldn't be completed. Try again or use another mode.")
        else:
            if self._cancel_requested.is_set():
                self.cancelled_operation.emit()
            else:
                self.succeeded.emit(result)
        finally:
            with self._lock:
                self._loop = None
                self._task = None


class CsvImportWorker(QThread):
    """Read and parse one CSV away from the UI thread."""

    loaded = Signal(object)
    failed = Signal()

    def __init__(
        self,
        path: str,
        parser: Callable[[str], object],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._parser = parser
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            text = Path(self._path).read_text(encoding="utf-8-sig")
            if self._cancelled:
                return
            batch = self._parser(text)
        except Exception:
            if not self._cancelled:
                self.failed.emit()
            return
        if not self._cancelled:
            self.loaded.emit(batch)


class SolveWorker(QThread):
    finished_outcome = Signal(object)

    def __init__(self, project: PlacementProject, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._cancellation = OptimizationCancellation()

    def cancel(self) -> None:
        self._cancellation.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self._cancellation.is_cancelled

    def run(self) -> None:
        try:
            outcome: SolveProjectOutcome = solve_project(self._project, self._cancellation)
        except Exception:
            # Native engine/loading failures must restore the UI, not leave a
            # calculation running forever. Raw exceptions may contain inputs.
            outcome = SolveProjectOutcome(
                OutcomeKind.CANCELLED if self.is_cancelled else OutcomeKind.UNAVAILABLE,
                "Calculation cancelled. Your inputs were kept."
                if self.is_cancelled
                else "Placements couldn't be calculated. Your inputs were kept; try again.",
            )
        self.finished_outcome.emit(outcome)
