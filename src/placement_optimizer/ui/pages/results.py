"""Results page: outcome banner, quiet warnings, conditional stats, and tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import (
    OutcomeKind,
    PlacementProject,
    SolveProjectOutcome,
)
from placement_optimizer.optimization import ObjectiveKind, OptimizationResult, SolveProof
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.widgets import Banner, StatCard, clear_layout, make_label

if TYPE_CHECKING:
    from placement_optimizer.ui.mainwindow import MainWindow

EMPTY_COPY = "Find placements to see results here."
RESULT_HEADER_HELP = {
    "Student": "The student who was assigned.",
    "Placement": "The location assigned to the student.",
    "Drive": "Driving time for this assignment.",
    "Distance": "Road distance for this assignment, when the travel source provides it.",
    "Choice": "The assigned location's rank in this student's choices.",
    "Changed": "Whether this differs from the previous placement supplied for the student.",
    "Location": "The placement location.",
}


def format_drive(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def format_distance(meters: int | None) -> str:
    if meters is None:
        return "—"
    return f"{meters / 1000:.1f} km"


def _ordinal(rank: int) -> str:
    teen = 10 <= rank % 100 <= 20
    suffix = "th" if teen else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


class ReadOnlyTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], rows: list[tuple[str, ...]]) -> None:
        super().__init__()
        self._headers = headers
        self._rows = rows

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation is Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._headers[section]
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.WhatsThisRole):
                return RESULT_HEADER_HELP.get(self._headers[section], "")
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[index.row()][index.column()]
        return None


class ResultsPage(QWidget):
    def __init__(self, controller: SessionController, host: MainWindow) -> None:
        super().__init__()
        self._controller = controller
        self._host = host
        self._outcome: SolveProjectOutcome | None = None
        self._project: PlacementProject | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(10)

        self.stack = QStackedWidget()
        empty = make_label(EMPTY_COPY, role="secondary")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(empty)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.banner = Banner()
        self.banner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.banner.hide()
        content_layout.addWidget(self.banner)

        self.warnings = make_label("", role="secondary", wrap=True)
        self.warnings.hide()
        content_layout.addWidget(self.warnings)

        self.recovery_actions = QWidget()
        self.recovery_actions.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        recovery_layout = QHBoxLayout(self.recovery_actions)
        recovery_layout.setContentsMargins(0, 0, 0, 0)
        recovery_layout.setSpacing(8)
        recovery_layout.addWidget(make_label("Things to review", role="secondary"))
        for text, step in (
            ("Rules", 2),
            ("Locations and capacity", 1),
            ("Travel times", 3),
        ):
            button = QPushButton(text)
            button.setProperty("kind", "quiet")
            button.clicked.connect(
                lambda _checked=False, destination=step: self._host.navigate(destination)
            )
            recovery_layout.addWidget(button)
        recovery_layout.addStretch(1)
        self.recovery_actions.hide()
        content_layout.addWidget(self.recovery_actions)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self.stat_longest = StatCard("Longest drive")
        self.stat_average = StatCard("Average drive")
        self.stat_choices = StatCard("Got one of their choices")
        self.stat_total = StatCard("Total driving")
        self.stat_longest.setToolTip("The longest assigned drive for any student.")
        self.stat_average.setToolTip("The average assigned drive per student.")
        self.stat_choices.setToolTip("Students assigned to one of the locations they ranked.")
        self.stat_total.setToolTip("All assigned driving times added together.")
        for card in (
            self.stat_longest,
            self.stat_average,
            self.stat_choices,
            self.stat_total,
        ):
            stats_row.addWidget(card, stretch=1)
        content_layout.addLayout(stats_row)

        self.toggle = QTabBar()
        self.toggle.addTab("By student")
        self.toggle.addTab("By location")
        self.toggle.setAccessibleName("Results grouping")
        content_layout.addWidget(self.toggle)

        self.tables = QStackedWidget()
        self.student_table = QTableView()
        self.student_table.setAccessibleName("Placements by student")
        self.location_table = QTableView()
        self.location_table.setAccessibleName("Placements by location")
        for table in (self.student_table, self.location_table):
            table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            table.verticalHeader().setVisible(False)
            table.setShowGrid(False)
            table.setAlternatingRowColors(True)
        self.tables.addWidget(self.student_table)
        self.tables.addWidget(self.location_table)
        self.toggle.currentChanged.connect(self.tables.setCurrentIndex)
        content_layout.addWidget(self.tables, stretch=1)

        self.capacity_box = QFrame()
        self.capacity_box.setProperty("card", "true")
        self.capacity_layout = QVBoxLayout(self.capacity_box)
        self.capacity_layout.setContentsMargins(16, 12, 16, 12)
        self.capacity_layout.setSpacing(6)
        self.capacity_box.setAccessibleName("Location capacity use")
        self.capacity_box.setAccessibleDescription(
            "Bars and numbers show assigned students out of each location's capacity."
        )
        capacity_scroll = self.capacity_scroll = QScrollArea()
        capacity_scroll.setWidgetResizable(True)
        capacity_scroll.setMinimumHeight(120)
        capacity_scroll.setMaximumHeight(180)
        capacity_scroll.setWidget(self.capacity_box)
        content_layout.addWidget(capacity_scroll)

        self.empty_result_space = QWidget()
        self.empty_result_space.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        content_layout.addWidget(self.empty_result_space, stretch=1)
        self.empty_result_space.hide()

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export CSV…")
        self.export_button.setToolTip("Save the current assignments in a spreadsheet-ready file.")
        self.export_button.clicked.connect(self._host.export_results)
        self.print_button = QPushButton("Print…")
        self.print_button.setToolTip(
            "Preview the assignments, choose how to arrange them, and print."
        )
        self.print_button.clicked.connect(self._host.print_results)
        actions.addWidget(self.export_button)
        actions.addWidget(self.print_button)
        actions.addStretch(1)
        content_layout.addLayout(actions)

        self.stack.addWidget(content)
        layout.addWidget(self.stack, stretch=1)

        controller.changed.connect(self.refresh_page)
        controller.session_replaced.connect(self.clear)
        self.refresh_page()

    # --- state ---------------------------------------------------------------

    @property
    def outcome(self) -> SolveProjectOutcome | None:
        return self._outcome

    @property
    def project(self) -> PlacementProject | None:
        return self._project

    def has_usable_result(self) -> bool:
        return bool(
            self._outcome
            and self._outcome.kind in (OutcomeKind.SUCCESS, OutcomeKind.NEEDS_ATTENTION)
            and self._outcome.result
            and self._outcome.result.proof in (SolveProof.OPTIMAL, SolveProof.FEASIBLE)
            and self._outcome.result.placements
            and self._project
        )

    def show_outcome(self, outcome: SolveProjectOutcome, project: PlacementProject) -> None:
        self._outcome = outcome
        self._project = project
        self.refresh_page()

    def clear(self) -> None:
        self._outcome = None
        self._project = None
        self.refresh_page()

    # --- rendering ---------------------------------------------------------------

    def refresh_page(self) -> None:
        outcome = self._outcome
        if outcome is None:
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        stale = self._controller.session.results_are_stale
        result = outcome.result

        usable = self.has_usable_result()
        if stale and usable:
            self.banner.show_message(
                "warning",
                "These placements predate your latest changes.",
                "Use Update placements to refresh them.",
            )
        else:
            kind, title, detail = self._banner_content(outcome)
            self.banner.show_message(kind, title, detail)

        bullets: list[str] = []
        if usable and result is not None:
            over_target = next(
                (
                    metric.value
                    for metric in result.metrics
                    if metric.objective is ObjectiveKind.OVER_TARGET_COUNT
                ),
                0,
            )
            if over_target and self._project is not None:
                target = round(self._project.optimization.commute_target_seconds / 60)
                noun = "student drives" if over_target == 1 else "students drive"
                bullets.append(f"{over_target} {noun} more than the {target}-minute target.")
            if result.unassigned_student_ids and self._project is not None:
                names = {student.id: student.name for student in self._project.students}
                joined = ", ".join(
                    names.get(student_id, student_id)
                    for student_id in result.unassigned_student_ids
                )
                bullets.append(f"Not placed: {joined}.")
        self.warnings.setText("\n".join(f"• {line}" for line in bullets))
        self.warnings.setVisible(bool(bullets))
        self.recovery_actions.setVisible(not usable)
        for widget in (
            self.stat_longest,
            self.stat_average,
            self.stat_choices,
            self.stat_total,
            self.toggle,
            self.tables,
            self.capacity_scroll,
        ):
            widget.setVisible(usable)

        if usable and result is not None and self._project is not None:
            self._render_result(result, self._project)
        else:
            self._render_empty_result()

        self.empty_result_space.setVisible(not self.has_usable_result())
        self.export_button.setEnabled(self.has_usable_result())
        self.print_button.setEnabled(self.has_usable_result())

    def _banner_content(self, outcome: SolveProjectOutcome) -> tuple[str, str, str]:
        result = outcome.result
        if outcome.kind is OutcomeKind.SUCCESS:
            return ("success", "Placements found — every rule is satisfied.", "")
        if outcome.kind is OutcomeKind.NEEDS_ATTENTION:
            if result is not None and result.unassigned_student_ids:
                count = len(result.unassigned_student_ids)
                noun = "student couldn't" if count == 1 else "students couldn't"
                return (
                    "warning",
                    f"{count} {noun} be placed.",
                    outcome.message,
                )
            if result is not None and result.proof is SolveProof.FEASIBLE:
                return (
                    "info",
                    "Placements found — they might improve with more calculation time.",
                    "Every rule is satisfied; a longer calculation time may find shorter drives.",
                )
            return ("warning", "Something needs attention.", outcome.message)
        if outcome.kind is OutcomeKind.INFEASIBLE:
            return ("error", "No arrangement fits.", outcome.message)
        if outcome.kind is OutcomeKind.NOT_SOLVED:
            return (
                "warning",
                "Not solved in time.",
                "Try more calculation time in More options, or fewer rules.",
            )
        if outcome.kind is OutcomeKind.INVALID:
            return (
                "error",
                "Something needs fixing before placements can be found.",
                outcome.message,
            )
        if outcome.kind is OutcomeKind.CANCELLED:
            return ("info", "Cancelled.", "Your previous results are unchanged.")
        return ("error", "That isn't available right now.", outcome.message)

    def _render_result(self, result: OptimizationResult, project: PlacementProject) -> None:
        student_names = {student.id: student.name for student in project.students}
        location_names = {location.id: location.name for location in project.locations}
        has_choices = bool(project.rules.preferences)
        has_prior = bool(project.rules.prior_assignments)
        has_distances = any(
            placement.distance_meters is not None for placement in result.placements
        )

        # Stats
        self.stat_longest.set_value(format_drive(result.maximum_commute_seconds))
        self.stat_average.set_value(format_drive(round(result.average_commute_seconds)))
        self.stat_total.set_value(format_drive(result.total_commute_seconds))
        if has_choices:
            choosers = {item.student_id for item in project.rules.preferences}
            satisfied = sum(
                1
                for placement in result.placements
                if placement.student_id in choosers and placement.preference_rank is not None
            )
            self.stat_choices.set_value(f"{satisfied} of {len(choosers)}")
            self.stat_choices.show()
        else:
            self.stat_choices.hide()

        # By-student table; unassigned students sort first.
        headers = ["Student", "Placement", "Drive"]
        if has_distances:
            headers.append("Distance")
        if has_choices:
            headers.append("Choice")
        if has_prior:
            headers.append("Changed")
        placements = sorted(
            result.placements,
            key=lambda placement: (placement.location_id is not None,),
        )
        rows = []
        for placement in placements:
            row = [
                student_names.get(placement.student_id, placement.student_id),
                (
                    location_names.get(placement.location_id or "", "Not placed")
                    if placement.location_id
                    else "Not placed"
                ),
                format_drive(placement.duration_seconds),
            ]
            if has_distances:
                row.append(format_distance(placement.distance_meters))
            if has_choices:
                row.append(
                    _ordinal(placement.preference_rank)
                    if placement.preference_rank is not None
                    else "—"
                )
            if has_prior:
                row.append("Yes" if placement.changed_from_prior else "")
            rows.append(tuple(row))
        self.student_table.setModel(ReadOnlyTableModel(headers, rows))
        self.student_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # By-location table.
        location_rows = []
        counts = dict(result.location_counts)
        for location in project.locations:
            members = [
                placement for placement in result.placements if placement.location_id == location.id
            ]
            if not members:
                row = [location.name, "—", ""]
                if has_distances:
                    row.append("")
                location_rows.append(tuple(row))
            for placement in members:
                row = [
                    location.name,
                    student_names.get(placement.student_id, placement.student_id),
                    format_drive(placement.duration_seconds),
                ]
                if has_distances:
                    row.append(format_distance(placement.distance_meters))
                location_rows.append(tuple(row))
        location_headers = ["Location", "Student", "Drive"]
        if has_distances:
            location_headers.append("Distance")
        self.location_table.setModel(ReadOnlyTableModel(location_headers, location_rows))
        self.location_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Capacity panel with restrained bars and numeric text.
        clear_layout(self.capacity_layout)
        for location in project.locations:
            assigned = counts.get(location.id, 0)
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(location.name)
            name.setMinimumWidth(140)
            bar = QProgressBar()
            bar.setRange(0, max(location.capacity, 1))
            bar.setValue(min(assigned, max(location.capacity, 1)))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            numbers = QLabel(f"{assigned} of {location.capacity}")
            numbers.setProperty("role", "secondary")
            row.addWidget(name)
            row.addWidget(bar, stretch=1)
            row.addWidget(numbers)
            self.capacity_layout.addLayout(row)

    def _render_empty_result(self) -> None:
        for card in (self.stat_longest, self.stat_average, self.stat_choices, self.stat_total):
            card.set_value("—")
        self.student_table.setModel(ReadOnlyTableModel(["Student", "Placement", "Drive"], []))
        self.location_table.setModel(ReadOnlyTableModel(["Location", "Student", "Drive"], []))
        clear_layout(self.capacity_layout)
