"""Review geocoded addresses and correct coordinates before routing."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import ResolvedPlace, TravelCoordinateReview
from placement_optimizer.ui.theme import tokens_for

_HEADERS = ("Type", "Name", "Entered", "Matched / issue", "Coordinates", "Source")
_HEADER_HELP = (
    "Whether this row is a student starting point or a placement location.",
    "The name kept on this computer. It was not sent to the map provider.",
    "The address entered in the project.",
    "The address found by the selected map option.",
    "Latitude and longitude used to calculate driving times. Double-click to correct them.",
    "Coordinates control the route. A coordinate override does not look up the entered address.",
)


@dataclass(slots=True)
class _ReviewRow:
    kind: str
    value: ResolvedPlace
    coordinates: str

    @property
    def coordinate(self) -> Coordinate | None:
        if _coordinate_issue(self.coordinates):
            return None
        # Display rounding is not a user correction. Preserve full provider
        # precision unless the editable text actually changes.
        if self.coordinates == _format_coordinate(self.value.coordinate):
            return self.value.coordinate
        return _parse_coordinate(self.coordinates)

    @property
    def is_correction(self) -> bool:
        return self.coordinate is not None and self.coordinate != self.value.coordinate


class AddressReviewModel(QAbstractTableModel):
    def __init__(self, review: TravelCoordinateReview) -> None:
        super().__init__()
        self.student_count = len(review.students)
        self.rows = [
            _ReviewRow("Student", value, _format_coordinate(value.coordinate))
            for value in review.students
        ] + [
            _ReviewRow("Location", value, _format_coordinate(value.coordinate))
            for value in review.locations
        ]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation is Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return _HEADERS[section]
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.WhatsThisRole):
                return _HEADER_HELP[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return flags | Qt.ItemFlag.ItemIsEditable if index.column() == 4 else flags

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        values = (
            row.kind,
            row.value.name,
            row.value.entered_address or "Coordinates provided",
            "Coordinates corrected"
            if row.is_correction
            else row.value.error or row.value.matched_address,
            row.coordinates,
            (
                "Coordinate correction — overrides address"
                if row.is_correction
                else row.value.source
            ),
        )
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return values[index.column()]
        issue = _coordinate_issue(row.coordinates) if index.column() == 4 else ""
        if role == Qt.ItemDataRole.ToolTipRole:
            return issue or values[index.column()]
        if role == Qt.ItemDataRole.BackgroundRole and issue:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                return QColor(tokens_for(app)["error_bg"])
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != 4:
            return False
        self.rows[index.row()].coordinates = str(value).strip()
        self.dataChanged.emit(self.index(index.row(), 3), self.index(index.row(), 5))
        return True

    def is_valid(self) -> bool:
        return all(not _coordinate_issue(row.coordinates) for row in self.rows)

    def corrections(self) -> tuple[tuple[str, str, Coordinate], ...]:
        result = []
        for row in self.rows:
            coordinate = row.coordinate
            if coordinate is not None and row.is_correction:
                result.append((row.kind, row.value.item_id, coordinate))
        return tuple(result)

    def review(self) -> TravelCoordinateReview:
        values = [
            ResolvedPlace(
                row.value.item_id,
                row.value.name,
                row.value.entered_address,
                row.value.matched_address,
                row.coordinate,
                (row.value.error or _coordinate_issue(row.coordinates))
                if _coordinate_issue(row.coordinates)
                else "",
                (
                    "Coordinate correction — overrides address"
                    if row.is_correction
                    else row.value.source
                ),
                coordinate_override=row.value.coordinate_override or row.is_correction,
            )
            for row in self.rows
        ]
        return TravelCoordinateReview(
            tuple(values[: self.student_count]),
            tuple(values[self.student_count :]),
        )


class AddressReviewDialog(QDialog):
    addressRepairRequested = Signal(str, str)
    retryRequested = Signal()

    def __init__(
        self,
        review: TravelCoordinateReview,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review addresses")
        self.setMinimumSize(820, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        intro = QLabel(
            "Check the matches before calculating driving times. Names stay on this computer. "
            "Coordinates control the route, even when an address is shown. "
            "Double-click Coordinates to correct a match, or edit the selected address and retry."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.model = AddressReviewModel(review)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 170)
        self.table.setAccessibleName("Address matches")
        layout.addWidget(self.table, stretch=1)
        actions = QHBoxLayout()
        repair = QPushButton("Edit selected address")
        repair.clicked.connect(self._repair_selected)
        retry = QPushButton("Retry unresolved addresses")
        retry.clicked.connect(self._retry)
        actions.addWidget(repair)
        actions.addWidget(retry)
        actions.addStretch(1)
        layout.addLayout(actions)
        unresolved = next(
            (index for index, row in enumerate(self.model.rows) if row.value.coordinate is None),
            0,
        )
        if self.model.rows:
            self.table.setCurrentIndex(self.model.index(unresolved, 4))
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use these coordinates")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.model.dataChanged.connect(lambda *_args: self._update_ok())
        self._update_ok()

    def _repair_selected(self) -> None:
        index = self.table.currentIndex()
        if index.isValid():
            row = self.model.rows[index.row()]
            self.addressRepairRequested.emit(row.kind, row.value.item_id)
            self.reject()

    def _retry(self) -> None:
        self.retryRequested.emit()
        self.reject()

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.model.is_valid())

    def corrections(self) -> tuple[tuple[str, str, Coordinate], ...]:
        return self.model.corrections()

    def review(self) -> TravelCoordinateReview:
        return self.model.review()


def _parse_coordinate(value: str) -> Coordinate:
    latitude, longitude = (part.strip() for part in value.split(",", maxsplit=1))
    return Coordinate(float(latitude), float(longitude))


def _coordinate_issue(value: str) -> str:
    try:
        _parse_coordinate(value)
    except (TypeError, ValueError):
        return "Enter latitude and longitude separated by a comma."
    return ""


def _format_coordinate(value: Coordinate | None) -> str:
    return "" if value is None else f"{value.latitude:.7f}, {value.longitude:.7f}"
