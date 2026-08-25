"""Off-thread placement calculation with safe cancellation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from placement_optimizer.application import PlacementProject, SolveProjectOutcome, solve_project
from placement_optimizer.optimization import OptimizationCancellation


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
        except (OSError, UnicodeError):
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
        outcome: SolveProjectOutcome = solve_project(self._project, self._cancellation)
        self.finished_outcome.emit(outcome)
