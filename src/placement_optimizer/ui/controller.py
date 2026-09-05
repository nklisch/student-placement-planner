"""Qt-facing bridge around the UI-neutral DraftSession.

DraftSession deliberately has no Qt imports, so widgets mutate it directly and
then call :meth:`SessionController.notify`. The main window and pages listen to
the single ``changed`` signal to refresh readiness, navigation status, and
page-level strips.

SnapshotUndo keeps one chronological history for roster, rules, and travel data.
A shared history is essential: a snapshot can restore related rows and rules,
so independently advancing page histories would overwrite later work.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from placement_optimizer.application import DraftGridSnapshot, DraftSession


class SnapshotUndo(QObject):
    """A minimal undo/redo stack over immutable state snapshots.

    ``capture`` must return a cheap immutable description of the state and
    ``restore`` must put it back. ``record`` is called *before* a mutation; a
    repeated ``tag`` coalesces rapid edits to the same target (for example
    re-typing in one cell) into a single undo step.
    """

    changed = Signal()

    def __init__(
        self,
        capture: Callable[[], object],
        restore: Callable[[object], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._capture = capture
        self._restore = restore
        self._undo: list[object] = []
        self._redo: list[object] = []
        self._last_tag: object = None
        self._generation = 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def record(self, tag: object = None) -> None:
        """Snapshot the current state as the undo point for an upcoming edit."""

        if tag is not None and tag == self._last_tag:
            return
        self._undo.append(self._capture())
        self._generation += 1
        self._redo.clear()
        self._last_tag = tag
        self.changed.emit()

    def bound_undo(self) -> Callable[[], bool]:
        """A toast may reverse only the operation it describes, never a later edit."""
        generation = self._generation

        def action() -> bool:
            return self.undo() if generation == self._generation else False

        return action

    def break_coalescing(self) -> None:
        self._last_tag = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        state = self._undo.pop()
        self._redo.append(self._capture())
        self._generation += 1
        self._restore(state)
        self._last_tag = None
        self.changed.emit()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        state = self._redo.pop()
        self._undo.append(self._capture())
        self._generation += 1
        self._generation += 1
        self._restore(state)
        self._last_tag = None
        self.changed.emit()
        return True

    def clear(self) -> None:
        if self._undo or self._redo:
            self._generation += 1
            self._undo.clear()
            self._redo.clear()
            self._last_tag = None
            self.changed.emit()


class SessionController(QObject):
    """Owns the active DraftSession and broadcasts UI-initiated changes."""

    changed = Signal()
    session_replaced = Signal()
    data_restored = Signal()
    notice = Signal(str)

    def __init__(self, session: DraftSession | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session or DraftSession()
        self.undo = SnapshotUndo(lambda: self._session.grid_snapshot(), self._restore_data, self)
        self.address_change_decision: Callable[[str], str] = lambda _name: "address"
        self._applying_import = False
        self._import_queue: deque[Callable[[], None]] = deque()

    @property
    def session(self) -> DraftSession:
        return self._session

    def set_session(self, session: DraftSession) -> None:
        self._session = session
        self.undo.clear()
        self.session_replaced.emit()
        self.changed.emit()

    def apply_import(self, operation: Callable[[], None]) -> None:
        """Keep import application + modal disposition one chronological operation.

        Qt modal dialogs still process worker completion signals. Defer another
        import until the current report is accepted/discarded, rather than letting
        Discard reverse a different newly completed import.
        """
        self._import_queue.append(operation)
        if self._applying_import:
            return
        self._applying_import = True
        try:
            while self._import_queue:
                self._import_queue.popleft()()
        finally:
            self._applying_import = False

    def _restore_data(self, snapshot: DraftGridSnapshot) -> None:
        self._session.restore_grid_snapshot(snapshot)
        self.data_restored.emit()
        self.changed.emit()

    def notify(self) -> None:
        """Call after any UI-initiated session mutation."""

        self.changed.emit()
