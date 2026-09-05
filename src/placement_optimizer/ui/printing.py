"""Print formatting and preview for placement results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html import escape

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import PlacementProject, SolveProjectOutcome
from placement_optimizer.optimization import Placement


class PrintLayout(StrEnum):
    BY_STUDENT = "by_student"
    BY_PLACEMENT = "by_placement"


@dataclass(frozen=True, slots=True)
class PrintOptions:
    layout: PrintLayout = PrintLayout.BY_STUDENT
    include_driving: bool = True


def build_results_print_html(
    outcome: SolveProjectOutcome,
    project: PlacementProject,
    options: PrintOptions,
    *,
    previous_result: bool = False,
) -> str:
    """Build the printable document independently of printer/UI state."""

    if outcome.result is None:
        raise ValueError("printable results are required")
    student_names = {student.id: student.name for student in project.students}
    location_names = {location.id: location.name for location in project.locations}
    placements = tuple(outcome.result.placements)
    has_distances = options.include_driving and any(
        placement.distance_meters is not None for placement in placements
    )

    if options.layout is PrintLayout.BY_PLACEMENT:
        content = _by_placement_html(
            placements,
            project,
            student_names,
            options.include_driving,
            has_distances,
        )
    else:
        content = _by_student_html(
            placements,
            student_names,
            location_names,
            options.include_driving,
            has_distances,
        )

    message = f"<p class='summary'>{escape(outcome.message)}</p>" if outcome.message else ""
    warning = (
        "<p><strong>Previous placements — these placements predate your latest changes. "
        "They may not satisfy the current roster, capacities, or rules.</strong></p>"
        if previous_result
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "body { color: #23251f; font-family: sans-serif; font-size: 10pt; }"
        "h1 { font-size: 17pt; margin: 0 0 4px 0; }"
        "h2 { font-size: 13pt; margin: 18px 0 5px 0; page-break-after: avoid; }"
        ".summary, .muted { color: #66645e; }"
        "table { border-collapse: collapse; width: 100%; margin-bottom: 10px; }"
        "th { text-align: left; border-bottom: 1px solid #8d8b85; padding: 5px 7px; }"
        "td { border-bottom: 1px solid #dedcd6; padding: 5px 7px; }"
        ".number { text-align: right; white-space: nowrap; }"
        "</style></head><body>"
        f"<h1>{escape(project.name)} — Placements</h1>{warning}{message}{content}"
        "</body></html>"
    )


def _by_student_html(
    placements: tuple[Placement, ...],
    student_names: dict[str, str],
    location_names: dict[str, str],
    include_driving: bool,
    has_distances: bool,
) -> str:
    headers = ["Student", "Placement"]
    if include_driving:
        headers.append("Drive")
    if has_distances:
        headers.append("Distance")
    rows = []
    for placement in sorted(
        placements,
        key=lambda item: student_names.get(item.student_id, item.student_id).casefold(),
    ):
        location = (
            location_names.get(placement.location_id, placement.location_id)
            if placement.location_id
            else "Not placed"
        )
        values = [student_names.get(placement.student_id, placement.student_id), location]
        if include_driving:
            values.append(_format_drive(placement.duration_seconds))
        if has_distances:
            values.append(_format_distance(placement.distance_meters))
        rows.append(_table_row(values, numeric_from=2))
    return _table(headers, rows, numeric_from=2)


def _by_placement_html(
    placements: tuple[Placement, ...],
    project: PlacementProject,
    student_names: dict[str, str],
    include_driving: bool,
    has_distances: bool,
) -> str:
    by_location: dict[str | None, list[Placement]] = {}
    for placement in placements:
        by_location.setdefault(placement.location_id, []).append(placement)

    sections: list[str] = []
    for location in project.locations:
        assigned = by_location.pop(location.id, [])
        sections.append(
            _placement_section(
                location.name,
                assigned,
                student_names,
                include_driving,
                has_distances,
                f"{len(assigned)} of {location.capacity}",
            )
        )
    unplaced = by_location.pop(None, [])
    if unplaced:
        sections.append(
            _placement_section(
                "Not placed",
                unplaced,
                student_names,
                include_driving,
                has_distances,
                str(len(unplaced)),
            )
        )
    # Retain a readable section if a result refers to a location no longer in
    # the displayed project. This is mainly useful for printing stale results.
    for location_id, assigned in sorted(by_location.items(), key=lambda item: str(item[0])):
        sections.append(
            _placement_section(
                str(location_id),
                assigned,
                student_names,
                include_driving,
                has_distances,
                str(len(assigned)),
            )
        )
    return "".join(sections)


def _placement_section(
    heading: str,
    placements: list[Placement],
    student_names: dict[str, str],
    include_driving: bool,
    has_distances: bool,
    count: str,
) -> str:
    headers = ["Student"]
    if include_driving:
        headers.append("Drive")
    if has_distances:
        headers.append("Distance")
    rows = []
    for placement in sorted(
        placements,
        key=lambda item: student_names.get(item.student_id, item.student_id).casefold(),
    ):
        values = [student_names.get(placement.student_id, placement.student_id)]
        if include_driving:
            values.append(_format_drive(placement.duration_seconds))
        if has_distances:
            values.append(_format_distance(placement.distance_meters))
        rows.append(_table_row(values, numeric_from=1))
    if not rows:
        rows.append(f"<tr><td colspan='{len(headers)}' class='muted'>No students</td></tr>")
    return f"<h2>{escape(heading)} <span class='muted'>— {escape(count)}</span></h2>" + _table(
        headers, rows, numeric_from=1
    )


def _table(headers: list[str], rows: list[str], *, numeric_from: int) -> str:
    rendered_headers = "".join(
        f"<th class='{'number' if index >= numeric_from else ''}'>{escape(value)}</th>"
        for index, value in enumerate(headers)
    )
    body = "".join(rows)
    return f"<table><thead><tr>{rendered_headers}</tr></thead><tbody>{body}</tbody></table>"


def _table_row(values: list[str], *, numeric_from: int) -> str:
    cells = "".join(
        f"<td class='{'number' if index >= numeric_from else ''}'>{escape(value)}</td>"
        for index, value in enumerate(values)
    )
    return f"<tr>{cells}</tr>"


def _format_drive(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes = round(seconds / 60)
    hours, remainder = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h" if not remainder else f"{hours} h {remainder} min"


def _format_distance(meters: int | None) -> str:
    return "—" if meters is None else f"{meters / 1000:.1f} km"


class ResultsPrintPreviewDialog(QDialog):
    """A compact native preview with only the choices that alter the document."""

    def __init__(
        self,
        outcome: SolveProjectOutcome,
        project: PlacementProject,
        parent: QWidget | None = None,
        *,
        previous_result: bool = False,
    ) -> None:
        super().__init__(parent)
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewWidget

        self._previous_result = previous_result
        self._outcome = outcome
        self._project = project
        self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self.setWindowTitle("Print preview — Placements")
        self.resize(960, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        options = QHBoxLayout()
        options.addWidget(QLabel("Arrange:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem("By student", PrintLayout.BY_STUDENT)
        self.layout_combo.addItem("By placement", PrintLayout.BY_PLACEMENT)
        self.layout_combo.setAccessibleName("Print arrangement")
        options.addWidget(self.layout_combo)
        self.include_driving = QCheckBox("Include drive time and distance")
        self.include_driving.setChecked(True)
        options.addWidget(self.include_driving)
        options.addStretch(1)
        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_in_button = QPushButton("Zoom in")
        self.fit_button = QPushButton("Fit page")
        options.addWidget(self.zoom_out_button)
        options.addWidget(self.zoom_in_button)
        options.addWidget(self.fit_button)
        layout.addLayout(options)

        self.preview = QPrintPreviewWidget(self._printer, self)
        self.preview.setAccessibleName("Placement print preview")
        self.preview.paintRequested.connect(self._paint)
        layout.addWidget(self.preview, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        print_button = QPushButton("Print…")
        print_button.setProperty("kind", "primary")
        print_button.clicked.connect(self._print)
        actions.addWidget(close_button)
        actions.addWidget(print_button)
        layout.addLayout(actions)

        self.layout_combo.currentIndexChanged.connect(self.preview.updatePreview)
        self.include_driving.toggled.connect(self.preview.updatePreview)
        self.zoom_out_button.clicked.connect(self.preview.zoomOut)
        self.zoom_in_button.clicked.connect(self.preview.zoomIn)
        self.fit_button.clicked.connect(self.preview.fitInView)

    def print_options(self) -> PrintOptions:
        try:
            layout = PrintLayout(str(self.layout_combo.currentData()))
        except ValueError:
            layout = PrintLayout.BY_STUDENT
        return PrintOptions(layout=layout, include_driving=self.include_driving.isChecked())

    def _document(self):
        from PySide6.QtGui import QTextDocument

        document = QTextDocument()
        document.setHtml(
            build_results_print_html(
                self._outcome,
                self._project,
                self.print_options(),
                previous_result=self._previous_result,
            )
        )
        return document

    def _paint(self, printer) -> None:
        self._document().print_(printer)

    def _print(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog

        dialog = QPrintDialog(self._printer, self)
        if dialog.exec():
            self._document().print_(self._printer)
