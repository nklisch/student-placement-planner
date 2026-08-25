"""Qt-facing bridge around the UI-neutral DraftSession.

DraftSession deliberately has no Qt imports, so widgets mutate it directly and
then call :meth:`SessionController.notify`. The main window and pages listen to
the single ``changed`` signal to refresh readiness, navigation status, and
page-level strips.

SnapshotUndo is the intentionally small scoped-undo store required by the UI
specification: table edits, paste blocks, and row operations capture immutable
snapshots before mutation. It is not a global command framework.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from placement_optimizer.application import DraftSession


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
        self._redo.clear()
        self._last_tag = tag
        self.changed.emit()

    def break_coalescing(self) -> None:
        self._last_tag = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        state = self._undo.pop()
        self._redo.append(self._capture())
        self._restore(state)
        self._last_tag = None
        self.changed.emit()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        state = self._redo.pop()
        self._undo.append(self._capture())
        self._restore(state)
        self._last_tag = None
        self.changed.emit()
        return True

    def clear(self) -> None:
        if self._undo or self._redo:
            self._undo.clear()
            self._redo.clear()
            self._last_tag = None
            self.changed.emit()


class SessionController(QObject):
    """Owns the active DraftSession and broadcasts UI-initiated changes."""

    changed = Signal()
    session_replaced = Signal()

    def __init__(self, session: DraftSession | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session or DraftSession()

    @property
    def session(self) -> DraftSession:
        return self._session

    def set_session(self, session: DraftSession) -> None:
        self._session = session
        self.session_replaced.emit()
        self.changed.emit()

    def notify(self) -> None:
        """Call after any UI-initiated session mutation."""

        self.changed.emit()
