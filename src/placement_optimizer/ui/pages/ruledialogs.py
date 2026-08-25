"""Native QDialog editors for the optional placement rules.

Ranked choices use a bulk student-by-rank grid because choices are normally
entered for many students at once. Together/apart use searchable multi-select;
pin/prohibit use student and location combos; commute limits combine one
global field with a collapsed per-student table; allowed locations pair one
student picker with location checkboxes.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.optimization import Preference

RANK_COUNT = 3
RANK_HEADERS = ("Student", "1st choice", "2nd choice", "3rd choice")


def person_label(person_id: str, names: dict[str, str]) -> str:
    name = names.get(person_id, "").strip()
    return f"{name} ({person_id})" if name and name != person_id else person_id


class _ComboDelegate(QStyledItemDelegate):
    """Combo box editor whose blank first entry clears the value."""

    def __init__(self, options: list[tuple[str, str]], blank: str = "—", parent=None) -> None:
        super().__init__(parent)
        self._options = options
        self._blank = blank

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItem(self._blank, "")
        for display, data in self._options:
            combo.addItem(display, data)
        return combo

    def setEditorData(self, editor, index) -> None:
        value = index.data(Qt.ItemDataRole.EditRole) or ""
        position = editor.findData(value)
        editor.setCurrentIndex(max(position, 0))

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.currentData())


class _MinutesDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        spin = QSpinBox(parent)
        spin.setRange(1, 999)
        spin.setSuffix(" min")
        return spin

    def setEditorData(self, editor, index) -> None:
        try:
            editor.setValue(int(index.data(Qt.ItemDataRole.EditRole) or 30))
        except (TypeError, ValueError):
            editor.setValue(30)

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.value())


class _ChoicesModel(QAbstractTableModel):
    """Students down the side, three ranked location choices across the top."""

    def __init__(
        self,
        students: list[tuple[str, str]],
        locations: list[tuple[str, str]],
        existing: tuple[Preference, ...],
    ) -> None:
        super().__init__()
        self._students = students
        self._location_names = dict(locations)
        current = {item.student_id: list(item.location_ids) for item in existing}
        self._choices: dict[str, list[str]] = {}
        for student_id, _name in students:
            picks = current.get(student_id, [])[:RANK_COUNT]
            self._choices[student_id] = picks + [""] * (RANK_COUNT - len(picks))

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._students)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else RANK_COUNT + 1

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation is Qt.Orientation.Horizontal:
            return RANK_HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        return base if index.column() == 0 else base | Qt.ItemFlag.ItemIsEditable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        student_id, name = self._students[index.row()]
        if index.column() == 0:
            if role == Qt.ItemDataRole.DisplayRole:
                return name or student_id
            return None
        pick = self._choices[student_id][index.column() - 1]
        if role == Qt.ItemDataRole.EditRole:
            return pick
        if role == Qt.ItemDataRole.DisplayRole:
            return self._location_names.get(pick, pick) if pick else ""
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() == 0:
            return False
        student_id, _name = self._students[index.row()]
        self._choices[student_id][index.column() - 1] = str(value or "")
        self.dataChanged.emit(index, index)
        return True

    def preferences(self) -> tuple[Preference, ...]:
        result = []
        for student_id, _name in self._students:
            picks: list[str] = []
            for value in self._choices[student_id]:
                if value and value not in picks:
                    picks.append(value)
            if picks:
                result.append(Preference(student_id, tuple(picks)))
        return tuple(result)


class RankedChoicesDialog(QDialog):
    def __init__(
        self,
        students: list[tuple[str, str]],
        locations: list[tuple[str, str]],
        existing: tuple[Preference, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ranked choices")
        self._model = _ChoicesModel(students, locations, existing)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        hint = QLabel(
            "Pick up to three locations for each student. Leave a cell blank for no choice."
        )
        hint.setProperty("role", "secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        table = QTableView()
        table.setModel(self._model)
        table.setItemDelegateForColumn(1, _ComboDelegate(list(locations), parent=table))
        table.setItemDelegateForColumn(2, _ComboDelegate(list(locations), parent=table))
        table.setItemDelegateForColumn(3, _ComboDelegate(list(locations), parent=table))
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumSize(560, 320)
        table.setToolTip(
            "Double-click a choice cell to select a location. Blank means no choice at that rank."
        )
        table.setAccessibleName("Ranked choices table")
        layout.addWidget(table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def preferences(self) -> tuple[Preference, ...]:
        return self._model.preferences()


class GroupRuleDialog(QDialog):
    """Pick two or more students for a together or apart rule."""

    def __init__(
        self,
        title: str,
        students: list[tuple[str, str]],
        preselected: tuple[str, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Search students")
        self._filter.setToolTip("Filter the list without changing which students are checked.")
        self._filter.setClearButtonEnabled(True)
        layout.addWidget(self._filter)
        self._list = QListWidget()
        self._list.setAccessibleName("Students")
        for student_id, name in students:
            item = QListWidgetItem(name or student_id)
            item.setData(Qt.ItemDataRole.UserRole, student_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if student_id in preselected else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        self._list.setMinimumSize(360, 280)
        layout.addWidget(self._list)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._filter.textChanged.connect(self._apply_filter)
        self._list.itemChanged.connect(lambda _item: self._update_ok())
        self._update_ok()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def _update_ok(self) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            len(self.selected_ids()) >= 2
        )

    def selected_ids(self) -> tuple[str, ...]:
        result = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.checkState() is Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return tuple(result)


class PairRuleDialog(QDialog):
    """Pick one student and one location for a pin or not-allowed rule."""

    def __init__(
        self,
        title: str,
        verb: str,
        students: list[tuple[str, str]],
        locations: list[tuple[str, str]],
        student_id: str = "",
        location_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(QLabel(verb))
        self.student_combo = QComboBox()
        self.student_combo.setToolTip("The student this rule applies to.")
        for sid, name in students:
            self.student_combo.addItem(name or sid, sid)
        self.location_combo = QComboBox()
        self.location_combo.setToolTip("The location this rule applies to.")
        for lid, name in locations:
            self.location_combo.addItem(name or lid, lid)
        if student_id:
            self.student_combo.setCurrentIndex(max(self.student_combo.findData(student_id), 0))
        if location_id:
            self.location_combo.setCurrentIndex(max(self.location_combo.findData(location_id), 0))
        student_row = QHBoxLayout()
        student_row.addWidget(QLabel("Student"))
        student_row.addWidget(self.student_combo, stretch=1)
        location_row = QHBoxLayout()
        location_row.addWidget(QLabel("Location"))
        location_row.addWidget(self.location_combo, stretch=1)
        layout.addLayout(student_row)
        layout.addLayout(location_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pair(self) -> tuple[str, str]:
        return (self.student_combo.currentData(), self.location_combo.currentData())


class _StudentLimitsModel(QAbstractTableModel):
    HEADERS = ("Student", "Driving limit")

    def __init__(self, students: list[tuple[str, str]], existing: tuple[tuple[str, int], ...]):
        super().__init__()
        self._students = students
        self._student_names = dict(students)
        self._rows: list[list[object]] = [
            [student_id, max(1, round(seconds / 60))] for student_id, seconds in existing
        ]

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation is Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        student_id, minutes = self._rows[index.row()]
        if index.column() == 0:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._student_names.get(student_id, student_id)
            if role == Qt.ItemDataRole.EditRole:
                return student_id
        else:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return minutes
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole:
            return False
        if index.column() == 0:
            self._rows[index.row()][0] = str(value)
        else:
            try:
                self._rows[index.row()][1] = max(1, int(value))
            except (TypeError, ValueError):
                return False
        self.dataChanged.emit(index, index)
        return True

    def add_row(self, student_id: str) -> None:
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append([student_id, 30])
        self.endInsertRows()

    def remove_row(self, row: int) -> None:
        if 0 <= row < len(self._rows):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._rows[row]
            self.endRemoveRows()

    def limits(self) -> tuple[tuple[str, int], ...]:
        seen: set[str] = set()
        result = []
        for student_id, minutes in self._rows:
            if student_id and student_id not in seen:
                seen.add(student_id)
                result.append((student_id, int(minutes) * 60))
        return tuple(result)


class CommuteLimitDialog(QDialog):
    """One global driving-time limit plus optional per-student limits."""

    def __init__(
        self,
        students: list[tuple[str, str]],
        maximum_seconds: int | None,
        student_limits: tuple[tuple[str, int], ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Limit driving time")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.global_check = QCheckBox("Limit everyone's driving time")
        self.global_check.setToolTip(
            "Prevent any placement whose driving time is above this limit."
        )
        self.global_spin = QSpinBox()
        self.global_spin.setToolTip("The longest drive allowed for every student.")
        self.global_spin.setRange(1, 999)
        self.global_spin.setSuffix(" minutes")
        global_row = QHBoxLayout()
        global_row.addWidget(self.global_check)
        global_row.addWidget(self.global_spin)
        global_row.addStretch(1)
        layout.addLayout(global_row)
        self.global_check.toggled.connect(self.global_spin.setEnabled)
        self.global_check.setChecked(maximum_seconds is not None)
        self.global_spin.setEnabled(maximum_seconds is not None)
        self.global_spin.setValue(round(maximum_seconds / 60) if maximum_seconds else 45)

        self.toggle = QToolButton()
        self.toggle.setText("Limits for specific students")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(bool(student_limits))
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if student_limits else Qt.ArrowType.RightArrow
        )
        layout.addWidget(self.toggle)

        self.detail = QWidget()
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        self._limits_model = _StudentLimitsModel(students, student_limits)
        table = QTableView()
        table.setModel(self._limits_model)
        table.setItemDelegateForColumn(0, _ComboDelegate(list(students), parent=table))
        table.setItemDelegateForColumn(1, _MinutesDelegate(table))
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumSize(420, 180)
        table.setAccessibleName("Per-student driving limits")
        detail_layout.addWidget(table)
        buttons_row = QHBoxLayout()
        add_button = QPushButton("Add a student limit")
        add_button.clicked.connect(lambda: self._limits_model.add_row(students[0][0]))
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(
            lambda: self._limits_model.remove_row(table.currentIndex().row())
        )
        buttons_row.addWidget(add_button)
        buttons_row.addWidget(remove_button)
        buttons_row.addStretch(1)
        detail_layout.addLayout(buttons_row)
        self.detail.setVisible(bool(student_limits))
        layout.addWidget(self.detail)
        self.toggle.toggled.connect(self._toggle_detail)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_detail(self, checked: bool) -> None:
        self.detail.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def result_limits(self) -> tuple[int | None, tuple[tuple[str, int], ...]]:
        maximum = self.global_spin.value() * 60 if self.global_check.isChecked() else None
        student_limits = self._limits_model.limits() if self.toggle.isChecked() else ()
        return maximum, student_limits


class AllowedLocationsDialog(QDialog):
    """Restrict individual students to a set of allowed locations."""

    def __init__(
        self,
        students: list[tuple[str, str]],
        locations: list[tuple[str, str]],
        existing: tuple[Preference, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Allowed locations only")
        self._locations = locations
        self._allowed: dict[str, set[str]] = {
            item.student_id: set(item.location_ids) for item in existing
        }
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(QLabel("Student"))
        self.student_combo = QComboBox()
        self.student_combo.setToolTip("Choose the student whose allowed locations you are editing.")
        for student_id, name in students:
            self.student_combo.addItem(name or student_id, student_id)
        row.addWidget(self.student_combo, stretch=1)
        layout.addLayout(row)
        hint = QLabel(
            "Leave every location checked to let this student go anywhere. "
            "Unchecking a location removes it from the places this student can go."
        )
        hint.setProperty("role", "secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._checks: list[QCheckBox] = []
        checks_box = QVBoxLayout()
        for location_id, name in locations:
            check = QCheckBox(name or location_id)
            check.setProperty("location_id", location_id)
            check.toggled.connect(lambda _checked: self._save_current())
            self._checks.append(check)
            checks_box.addWidget(check)
        layout.addLayout(checks_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.student_combo.currentIndexChanged.connect(lambda _i: self._load_current())
        self._load_current()
        self.setMinimumWidth(380)

    def _current_student(self) -> str:
        return self.student_combo.currentData()

    def _load_current(self) -> None:
        self._loading = True
        allowed = self._allowed.get(self._current_student())
        for check in self._checks:
            checked = allowed is None or check.property("location_id") in allowed
            check.setChecked(checked)
        self._loading = False

    def _save_current(self) -> None:
        if self._loading:
            return
        checked = {check.property("location_id") for check in self._checks if check.isChecked()}
        student_id = self._current_student()
        if len(checked) == len(self._checks):
            self._allowed.pop(student_id, None)
        else:
            self._allowed[student_id] = checked

    def eligible(self) -> tuple[Preference, ...]:
        self._save_current()
        order = [location_id for location_id, _name in self._locations]
        return tuple(
            Preference(
                student_id,
                tuple(location_id for location_id in order if location_id in allowed),
            )
            for student_id, allowed in self._allowed.items()
        )
