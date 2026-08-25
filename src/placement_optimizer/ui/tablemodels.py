"""QAbstractTableModel implementations backed by DraftSession.

Validation state lives in the models (issue maps cached per session version);
views and delegates only render it. All three editable grids — students,
locations, and manual driving times — share the same interaction contract:
a live new-row position on roster tables, raw-text retention for invalid
input, TSV paste blocks as single undo operations, and snapshot undo scoped
to the grid.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication

from placement_optimizer.application import DraftArea, DraftGridSnapshot, DraftSession
from placement_optimizer.ui.controller import SessionController, SnapshotUndo
from placement_optimizer.ui.help_content import LOCATION_FIELD_HELP, STUDENT_FIELD_HELP
from placement_optimizer.ui.theme import LIGHT, tokens_for

_NO_ROUTE_WORDS = {"x", "-", "no route"}


def build_issue_map(session: DraftSession, area: DraftArea) -> dict[str, dict[str, str]]:
    """Map ``row_key -> {field: message}`` for one draft area."""

    result: dict[str, dict[str, str]] = {}
    for issue in session.readiness().issues:
        if issue.area is area and issue.row_key:
            result.setdefault(issue.row_key, {})[issue.field or ""] = issue.message
    return result


def capture_grid_state(session: DraftSession) -> DraftGridSnapshot:
    """Snapshot everything the editable grids can affect."""

    return session.grid_snapshot()


def restore_grid_state(session: DraftSession, state: DraftGridSnapshot) -> None:
    """Restore a grid snapshot through the public draft-session boundary."""

    session.restore_grid_snapshot(state)


def _tokens() -> dict[str, str]:
    app = QGuiApplication.instance()
    if isinstance(app, QApplication):
        return tokens_for(app)
    return dict(LIGHT)


def _tsv_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    grid = [line.split("\t") for line in lines]
    # Excel adds a trailing newline for full-row copies; drop all-empty tails.
    while grid and all(not cell.strip() for cell in grid[-1]):
        grid.pop()
    return grid


class RosterTableModel(QAbstractTableModel):
    """Base model for the Students and Locations grids.

    The final row is a live "new row": typing into it appends a real row with
    an auto-filled ID and then applies the typed value.
    """

    AREA: DraftArea
    HEADERS: tuple[str, ...] = ()
    HEADER_HELP: tuple[str, ...] = ()
    FIELDS: tuple[str, ...] = ()
    GHOST_HINT = "Type to add a row."
    ID_COLUMN = 1

    def __init__(self, controller: SessionController, parent: QAbstractTableModel | None = None):
        super().__init__(parent)
        self._controller = controller
        self.undo = SnapshotUndo(
            lambda: capture_grid_state(self._session),
            self._restore,
            self,
        )
        self._issue_version = -1
        self._issue_cache: dict[str, dict[str, str]] = {}
        self._edited_id_keys: set[str] = set()

    # --- session access -------------------------------------------------

    @property
    def _session(self) -> DraftSession:
        return self._controller.session

    def _rows(self) -> list:
        raise NotImplementedError

    def _add_draft(self):
        raise NotImplementedError

    def _update_row(self, index: int, field: str, value: str) -> None:
        raise NotImplementedError

    def _remove_rows(self, indexes: list[int]) -> None:
        raise NotImplementedError

    # --- structure ------------------------------------------------------

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows()) + 1

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.FIELDS)

    def _is_ghost(self, row: int) -> bool:
        return row == len(self._rows())

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation is Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self.HEADERS[section]
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.WhatsThisRole):
                return self.HEADER_HELP[section]
        elif role == Qt.ItemDataRole.DisplayRole:
            return "+" if self._is_ghost(section) else str(section + 1)
        elif role == Qt.ItemDataRole.ToolTipRole and self._is_ghost(section):
            return self.GHOST_HINT
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    # --- data -----------------------------------------------------------

    def _issues(self) -> dict[str, dict[str, str]]:
        session = self._session
        if self._issue_version != session.version:
            self._issue_version = session.version
            self._issue_cache = build_issue_map(session, self.AREA)
        return self._issue_cache

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if self._is_ghost(row):
            if role == Qt.ItemDataRole.ToolTipRole:
                return self.GHOST_HINT
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return ""
            return None

        draft = self._rows()[row]
        field = self.FIELDS[column]
        value = getattr(draft, field)
        issue = self._issues().get(draft.key, {}).get(field)

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return value
        if role == Qt.ItemDataRole.ToolTipRole and issue:
            return issue
        if role == Qt.ItemDataRole.BackgroundRole and issue:
            tokens = _tokens()
            # Blank required cells read as "missing"; typed-but-invalid as errors.
            return QColor(tokens["warning_bg"] if not value.strip() else tokens["error_bg"])
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == self.ID_COLUMN and draft.key not in self._edited_id_keys:
                return QColor(_tokens()["secondary"])
            if issue and value.strip():
                return QColor(_tokens()["error"])
        return None

    def setData(self, index: QModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row, column = index.row(), index.column()
        field = self.FIELDS[column]
        text = "" if value is None else str(value)

        if self._is_ghost(row):
            self.undo.record()
            position = len(self._rows())
            self.beginInsertRows(QModelIndex(), position, position)
            self._add_draft()
            self.endInsertRows()
            self._apply_value(position, field, text, record=False)
            return True

        self._apply_value(row, field, text, record=True)
        return True

    def _apply_value(self, row: int, field: str, text: str, *, record: bool) -> None:
        draft = self._rows()[row]
        if getattr(draft, field) == text:
            return
        if record:
            self.undo.record(tag=("cell", draft.key, field))
        if field == "id":
            self._edited_id_keys.add(draft.key)
        self._update_row(row, field, text)
        changed = self.index(row, self.FIELDS.index(field))
        self.dataChanged.emit(changed, changed)
        self._controller.notify()

    # --- block operations ------------------------------------------------

    def clear_indexes(self, indexes: list[QModelIndex]) -> None:
        targets = sorted(
            {(i.row(), i.column()) for i in indexes if i.isValid() and not self._is_ghost(i.row())}
        )
        if not targets:
            return
        self.undo.record()
        for row, column in targets:
            self._apply_value(row, self.FIELDS[column], "", record=False)
        self._controller.notify()

    def paste_block(self, start_row: int, start_column: int, text: str) -> None:
        grid = _tsv_rows(text)
        if not grid:
            return
        self.undo.record()
        last_column = self.columnCount() - 1
        for row_offset, values in enumerate(grid):
            target = start_row + row_offset
            while target >= len(self._rows()):
                self._add_draft()
            room = last_column - start_column + 1
            fitting, overflow = values[:room], values[room:]
            for column_offset, value in enumerate(fitting):
                field = self.FIELDS[start_column + column_offset]
                self._apply_value(target, field, value, record=False)
            if overflow:
                # Extra columns merge into the final cell so nothing is lost;
                # a split "lat <tab> lon" paste becomes a valid coordinate pair.
                field = self.FIELDS[last_column]
                current = getattr(self._rows()[target], field)
                merged = f"{current}, {', '.join(overflow)}" if current else ", ".join(overflow)
                self._apply_value(target, self.FIELDS[last_column], merged, record=False)
        self.refresh()
        self._controller.notify()

    def delete_rows(self, indexes: list[int]) -> bool:
        """Remove real rows; return True when rule cleanup also happened."""

        real = sorted({i for i in indexes if 0 <= i < len(self._rows())})
        if not real:
            return False
        self.undo.record()
        rules_before = self._session.rules
        self._remove_rows(real)
        self.refresh()
        self._controller.notify()
        return rules_before != self._session.rules

    def issue_index(self, row_key: str, field: str) -> QModelIndex:
        for row, draft in enumerate(self._rows()):
            if draft.key == row_key and field in self.FIELDS:
                return self.index(row, self.FIELDS.index(field))
        return QModelIndex()

    def refresh(self) -> None:
        self._issue_version = -1
        self.beginResetModel()
        self.endResetModel()

    def hard_reset(self) -> None:
        """Session was replaced: drop undo history and cached issues."""

        self.undo.clear()
        self._edited_id_keys.clear()
        self.refresh()

    def _restore(self, state: DraftGridSnapshot) -> None:
        restore_grid_state(self._session, state)
        self._issue_version = -1
        self.refresh()
        self._controller.notify()


class StudentsTableModel(RosterTableModel):
    AREA = DraftArea.STUDENTS
    HEADERS = ("Name", "ID", "Address", "Coordinates")
    HEADER_HELP = STUDENT_FIELD_HELP
    FIELDS = ("name", "id", "address", "coordinates")
    GHOST_HINT = "Type to add a student."

    def _rows(self) -> list:
        return self._session.students

    def _add_draft(self):
        return self._session.add_student()

    def _update_row(self, index: int, field: str, value: str) -> None:
        self._session.update_student(index, **{field: value})

    def _remove_rows(self, indexes: list[int]) -> None:
        self._session.remove_students(indexes)


class LocationsTableModel(RosterTableModel):
    AREA = DraftArea.LOCATIONS
    HEADERS = ("Name", "ID", "Capacity", "Minimum", "Address", "Coordinates")
    HEADER_HELP = LOCATION_FIELD_HELP
    FIELDS = ("name", "id", "capacity", "minimum_capacity", "address", "coordinates")
    GHOST_HINT = "Type to add a location."

    def _rows(self) -> list:
        return self._session.locations

    def _add_draft(self):
        return self._session.add_location()

    def _update_row(self, index: int, field: str, value: str) -> None:
        self._session.update_location(index, **{field: value})

    def _remove_rows(self, indexes: list[int]) -> None:
        self._session.remove_locations(indexes)


class ManualTimesModel(QAbstractTableModel):
    """The driving-minutes grid: students down the side, locations across the top.

    Cells store raw text in ``DraftSession.manual_times``; the session decides
    what is valid. Blank means "not filled yet", ``x`` means no route.
    """

    def __init__(self, controller: SessionController, parent: QAbstractTableModel | None = None):
        super().__init__(parent)
        self._controller = controller
        self.undo = SnapshotUndo(
            lambda: capture_grid_state(self._session),
            self._restore,
            self,
        )
        self._issue_version = -1
        self._issue_cache: dict[str, str] = {}

    @property
    def _session(self) -> DraftSession:
        return self._controller.session

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._session.students)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._session.locations)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def _pair_key(self, row: int, column: int) -> tuple[str, str]:
        return (self._session.students[row].key, self._session.locations[column].key)

    def _issues(self) -> dict[str, str]:
        session = self._session
        if self._issue_version != session.version:
            self._issue_version = session.version
            self._issue_cache = {
                issue.row_key: issue.message
                for issue in session.readiness().issues
                if issue.area is DraftArea.TRAVEL and issue.row_key
            }
        return self._issue_cache

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self._pair_key(index.row(), index.column())
        raw = self._session.manual_times.get(key, "")
        issue = self._issues().get(f"{key[0]}:{key[1]}")

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return raw
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if issue:
                return issue
            if not raw.strip():
                return "Enter driving minutes, or x for no route."
        if role == Qt.ItemDataRole.BackgroundRole and issue:
            return QColor(_tokens()["error_bg"])
        if role == Qt.ItemDataRole.ForegroundRole and issue:
            return QColor(_tokens()["error"])
        return None

    def setData(self, index: QModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        text = "" if value is None else str(value)
        key = self._pair_key(index.row(), index.column())
        if self._session.manual_times.get(key, "") == text.strip():
            return False
        self.undo.record(tag=("cell", key))
        self._session.set_manual_time(key[0], key[1], text)
        self.dataChanged.emit(index, index)
        self._controller.notify()
        return True

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation is Qt.Orientation.Horizontal:
            draft = self._session.locations[section]
            label = draft.name.strip() or draft.id.strip() or f"Location {section + 1}"
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                return label
        else:
            draft = self._session.students[section]
            label = draft.name.strip() or draft.id.strip() or f"Student {section + 1}"
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                return label
        return None

    # --- block operations ------------------------------------------------

    def clear_indexes(self, indexes: list[QModelIndex]) -> None:
        targets = {(i.row(), i.column()) for i in indexes if i.isValid()}
        if not targets:
            return
        self.undo.record()
        for row, column in sorted(targets):
            key = self._pair_key(row, column)
            self._session.set_manual_time(key[0], key[1], "")
            self.dataChanged.emit(self.index(row, column), self.index(row, column))
        self._controller.notify()

    def paste_block(self, start_row: int, start_column: int, text: str) -> None:
        grid = _tsv_rows(text)
        if not grid:
            return
        self.undo.record()
        last_column = self.columnCount() - 1
        for row_offset, values in enumerate(grid):
            target_row = start_row + row_offset
            if target_row >= self.rowCount():
                break  # the grid size follows the rosters; extra rows do not land
            room = last_column - start_column + 1
            fitting, overflow = values[:room], values[room:]
            for column_offset, value in enumerate(fitting):
                self._set_cell(target_row, start_column + column_offset, value)
            if overflow:
                current = self._session.manual_times.get(
                    self._pair_key(target_row, last_column), ""
                )
                merged = f"{current}, {', '.join(overflow)}" if current else ", ".join(overflow)
                self._set_cell(target_row, last_column, merged)
        self._controller.notify()

    def _set_cell(self, row: int, column: int, value: str) -> None:
        key = self._pair_key(row, column)
        self._session.set_manual_time(key[0], key[1], value)
        changed = self.index(row, column)
        self.dataChanged.emit(changed, changed)

    def completeness(self) -> tuple[int, int]:
        total = self.rowCount() * self.columnCount()
        filled = 0
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                if self._session.manual_times.get(self._pair_key(row, column), "").strip():
                    filled += 1
        return filled, total

    def refresh(self) -> None:
        self._issue_version = -1
        self.beginResetModel()
        self.endResetModel()

    def hard_reset(self) -> None:
        self.undo.clear()
        self.refresh()

    def _restore(self, state: DraftGridSnapshot) -> None:
        restore_grid_state(self._session, state)
        self._issue_version = -1
        self.refresh()
        self._controller.notify()
