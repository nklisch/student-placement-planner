"""QTableView subclass implementing the spreadsheet interaction contract.

Single click selects; Enter/F2/double click/typing edit; Tab and Shift+Tab
commit and move horizontally; Enter commits and moves down; Escape cancels;
Delete/Backspace clears; Ctrl/Cmd+C copies TSV; Ctrl/Cmd+V pastes a TSV block
anchored at the active cell; a dropped CSV file behaves like Import CSV.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QStyledItemDelegate, QTableView


class GridDelegate(QStyledItemDelegate):
    """Commits on Return/Enter and then moves the cursor down one row."""

    def __init__(self, view: PasteTableView) -> None:
        super().__init__(view)
        self._view = view

    def eventFilter(self, editor: object, event: object) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QKeyEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
            # Let the editor close before moving, or the move reopens editing.
            QTimer.singleShot(0, self._view.move_cursor_down)
            return True
        return super().eventFilter(editor, event)


class PasteTableView(QTableView):
    """A grid view with TSV copy/paste, cell clearing, and CSV file drops."""

    fileDropped = Signal(str)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setCornerButtonEnabled(False)
        self.setItemDelegate(GridDelegate(self))
        self.verticalHeader().setDefaultSectionSize(32)
        self.verticalHeader().setMinimumSectionSize(28)
        self.horizontalHeader().setHighlightSections(False)
        self.setAcceptDrops(True)

    # --- keyboard contract ----------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
            return
        if (
            event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.clear_selection()
            return
        super().keyPressEvent(event)

    def move_cursor_down(self) -> None:
        target = self.moveCursor(
            QAbstractItemView.CursorAction.MoveDown,
            Qt.KeyboardModifier.NoModifier,
        )
        if target.isValid():
            self.setCurrentIndex(target)

    def clear_selection(self) -> None:
        model = self.model()
        if model is not None and hasattr(model, "clear_indexes"):
            model.clear_indexes(self.selectedIndexes())

    # --- clipboard -------------------------------------------------------

    def copy_selection(self) -> None:
        indexes = [i for i in self.selectedIndexes() if i.isValid()]
        if not indexes:
            return
        top = min(i.row() for i in indexes)
        left = min(i.column() for i in indexes)
        bottom = max(i.row() for i in indexes)
        right = max(i.column() for i in indexes)
        model = self.model()
        lines = []
        for row in range(top, bottom + 1):
            cells = []
            for column in range(left, right + 1):
                value = model.index(row, column).data(Qt.ItemDataRole.DisplayRole)
                cells.append("" if value is None else str(value))
            lines.append("\t".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))

    def paste_from_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text:
            return
        anchor = self.currentIndex()
        row = anchor.row() if anchor.isValid() else 0
        column = anchor.column() if anchor.isValid() else 0
        model = self.model()
        if model is not None and hasattr(model, "paste_block"):
            model.paste_block(max(row, 0), max(column, 0), text)

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.selectedIndexes() if i.isValid()})

    # --- CSV drops ---------------------------------------------------------

    def dragEnterEvent(self, event: object) -> None:
        mime = event.mimeData() if hasattr(event, "mimeData") else None
        if isinstance(mime, QMimeData) and any(
            url.isLocalFile() and url.fileName().lower().endswith((".csv", ".tsv"))
            for url in mime.urls()
        ):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: object) -> None:
        mime = event.mimeData() if hasattr(event, "mimeData") else None
        if isinstance(mime, QMimeData):
            for url in mime.urls():
                if url.isLocalFile() and url.fileName().lower().endswith((".csv", ".tsv")):
                    self.fileDropped.emit(url.toLocalFile())
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)
