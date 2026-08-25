"""Shared roster page for Students and Locations.

Both pages are the same spreadsheet surface with different columns, copy, and
CSV parsers: a header with actions and a quiet count, a slim clickable issue
strip, contextual notes, and an empty state that offers paste, import, or
typing the first row.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import DraftIssue
from placement_optimizer.projects import ImportBatch, parse_locations_csv, parse_students_csv
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.tablemodels import (
    LocationsTableModel,
    RosterTableModel,
    StudentsTableModel,
)
from placement_optimizer.ui.tableview import PasteTableView
from placement_optimizer.ui.widgets import EmptyState, InfoStrip, make_label
from placement_optimizer.ui.workers import CsvImportWorker

if TYPE_CHECKING:
    from placement_optimizer.ui.mainwindow import MainWindow


class IssueStrip(QFrame):
    """A slim strip of clickable issues that jump to their cells."""

    def __init__(self, on_jump: Callable[[DraftIssue], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("banner", "warning")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 4, 12, 4)
        self._layout.setSpacing(6)
        self._on_jump = on_jump
        self.hide()

    def set_issues(self, issues: list[DraftIssue], describe: Callable[[DraftIssue], str]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not issues:
            self.hide()
            return
        for issue in issues[:3]:
            button = QToolButton(self)
            button.setText(describe(issue))
            button.clicked.connect(lambda _checked=False, i=issue: self._on_jump(i))
            self._layout.addWidget(button)
        if len(issues) > 3:
            more = make_label(f"…and {len(issues) - 3} more", role="secondary")
            self._layout.addWidget(more)
        self._layout.addStretch(1)
        self.show()


class RosterPage(QWidget):
    TITLE = ""
    DESCRIPTION = ""
    ADD_TEXT = ""
    COUNT_SINGULAR = "row"
    COUNT_PLURAL = "rows"
    EMPTY_TITLE = ""

    def __init__(self, controller: SessionController, host: MainWindow) -> None:
        super().__init__()
        self._controller = controller
        self._host = host
        self._import_worker: CsvImportWorker | None = None
        self._import_session = None
        self.model: RosterTableModel = self._make_model(controller)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.addWidget(make_label(self.TITLE, role="title"))
        title_block.addWidget(make_label(self.DESCRIPTION, role="secondary", wrap=True))
        header.addLayout(title_block, stretch=1)
        self.count_label = make_label("", role="secondary")
        header.addWidget(self.count_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.add_button = QPushButton(self.ADD_TEXT)
        self.add_button.setToolTip("Add a blank row. Its ID is filled in automatically.")
        self.add_button.clicked.connect(self.add_row)
        self.paste_button = QPushButton("Paste from spreadsheet")
        self.paste_button.setToolTip(
            "Paste tab-separated rows from a spreadsheet, starting at the selected cell."
        )
        self.paste_button.clicked.connect(self.paste_from_excel)
        self.import_button = QPushButton("Import CSV…")
        self.import_button.setToolTip(
            "Import a CSV file. Rows with problems stay visible so you can repair them."
        )
        self.import_button.clicked.connect(self.import_csv)
        actions.addWidget(self.add_button)
        actions.addWidget(self.paste_button)
        actions.addWidget(self.import_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.issue_strip = IssueStrip(self._jump_to_issue)
        layout.addWidget(self.issue_strip)
        self.note_strip = InfoStrip()
        layout.addWidget(self.note_strip)

        self.table = PasteTableView()
        self.table.setModel(self.model)
        self._configure_columns()
        self.table.fileDropped.connect(self.import_csv_path)
        self.table.setAccessibleName(f"{self.TITLE} table")
        self.table.setAccessibleDescription(
            "Editable spreadsheet. Hover column headings for field definitions."
        )

        self.empty_state = EmptyState(self.EMPTY_TITLE)
        self.empty_state.add_action("Paste from spreadsheet", self.paste_from_excel)
        self.empty_state.add_action("Import CSV…", self.import_csv)
        self.empty_state.add_action("Type the first row", self.add_row)
        self.empty_state.add_action("Load sample data", self._host.load_sample_data, quiet=True)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack, stretch=1)

        controller.changed.connect(self.refresh_page)
        controller.session_replaced.connect(self._on_session_replaced)
        self.refresh_page()

    # --- model factory ----------------------------------------------------

    def _make_model(self, controller: SessionController) -> RosterTableModel:
        raise NotImplementedError

    def _configure_columns(self) -> None:
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    # --- actions -----------------------------------------------------------

    def add_row(self) -> None:
        """Focus the live new row so keyboard-only users can start typing."""

        self.stack.setCurrentWidget(self.table)
        ghost = self.model.index(self.model.rowCount() - 1, 0)
        self.table.setCurrentIndex(ghost)
        self.table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.table.edit(ghost)

    def paste_from_excel(self) -> None:
        self.stack.setCurrentWidget(self.table)
        if not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        self.table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.table.paste_from_clipboard()

    def delete_selected_rows(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        rules_cleaned = self.model.delete_rows(rows)
        if rules_cleaned:
            self._host.show_toast(
                "Rules that mentioned removed rows were updated.",
                "Undo",
                self.model.undo.undo,
            )

    # --- CSV import ---------------------------------------------------------

    def import_csv(self) -> None:
        path = self._host.ask_open_csv(self)
        if path:
            self.import_csv_path(path)

    def import_csv_path(self, path: str) -> None:
        if self._import_worker is not None:
            self._host.show_toast("An import is already in progress.")
            return
        self._import_session = self._controller.session
        self._import_worker = CsvImportWorker(path, self._parse, self)
        self._import_worker.loaded.connect(self._apply_import)
        self._import_worker.failed.connect(self._import_failed)
        self._import_worker.finished.connect(self._import_finished)
        self.import_button.setEnabled(False)
        self.import_button.setText("Importing…")
        self._import_worker.start()

    def _apply_import(self, batch: ImportBatch) -> None:
        if self._import_session is not self._controller.session:
            return
        if not batch.draft_rows:
            message = batch.issues[0].message if batch.issues else "No rows were found."
            self._host.show_toast(message)
            return

        self.model.undo.record()
        added = 0
        for draft_row in batch.draft_rows:
            self._add_import_row(draft_row.as_dict())
            added += 1
        self.model.refresh()
        self._controller.notify()

        if batch.error_count:
            self._host.report_import(
                accepted=added - batch.error_count,
                kept=batch.error_count,
                on_fix=self.reveal_first_issue,
                on_discard=self.model.undo.undo,
            )
        else:
            self._host.show_toast(f"Imported {added} {self._count_word(added)}.")

    def _import_failed(self) -> None:
        self._host.show_toast("That file couldn't be read. Check it and try again.")

    def _import_finished(self) -> None:
        worker = self._import_worker
        self._import_worker = None
        self._import_session = None
        self.import_button.setEnabled(True)
        self.import_button.setText("Import CSV…")
        if worker is not None:
            worker.deleteLater()
        self._host.import_worker_finished()

    def cancel_import(self) -> None:
        if self._import_worker is not None:
            self._import_worker.cancel()

    def has_active_import(self) -> bool:
        return self._import_worker is not None

    def _parse(self, text: str) -> ImportBatch:
        raise NotImplementedError

    def _add_import_row(self, values: dict[str, str]) -> None:
        raise NotImplementedError

    # --- refresh -------------------------------------------------------------

    def refresh_page(self) -> None:
        rows = len(self.model._rows())
        self.count_label.setText(f"{rows} {self._count_word(rows)}" if rows else "")
        self.stack.setCurrentWidget(self.table if rows else self.empty_state)
        issues = [
            issue
            for issue in self._controller.session.readiness().issues
            if issue.area is self.model.AREA
        ]
        self.issue_strip.set_issues(issues, self._describe_issue)
        self.note_strip.show_text(self._note_text())

    def _count_word(self, count: int) -> str:
        return self.COUNT_SINGULAR if count == 1 else self.COUNT_PLURAL

    def _describe_issue(self, issue: DraftIssue) -> str:
        row_label = issue.row_key or ""
        for index, draft in enumerate(self.model._rows()):
            if draft.key == issue.row_key:
                name = getattr(draft, "name", "").strip()
                row_label = name or f"Row {index + 1}"
                break
        return f"{row_label}: {issue.message}"

    def _note_text(self) -> str:
        return ""

    def _jump_to_issue(self, issue: DraftIssue) -> None:
        if not issue.row_key or not issue.field:
            return
        index = self.model.issue_index(issue.row_key, issue.field)
        if index.isValid():
            self.stack.setCurrentWidget(self.table)
            self.table.setCurrentIndex(index)
            self.table.scrollTo(index)
            self.table.setFocus(Qt.FocusReason.OtherFocusReason)

    def reveal_first_issue(self) -> None:
        issues = [
            issue
            for issue in self._controller.session.readiness().issues
            if issue.area is self.model.AREA
        ]
        if issues:
            self._jump_to_issue(issues[0])

    def _on_session_replaced(self) -> None:
        self.cancel_import()
        self._import_session = None
        self.model.hard_reset()
        self.refresh_page()


class StudentsPage(RosterPage):
    TITLE = "Students"
    DESCRIPTION = (
        "The students who need a placement. Type rows, paste from a spreadsheet, or import a CSV."
    )
    ADD_TEXT = "Add student"
    COUNT_SINGULAR = "student"
    COUNT_PLURAL = "students"
    EMPTY_TITLE = "Add your students"

    def _make_model(self, controller: SessionController) -> RosterTableModel:
        return StudentsTableModel(controller)

    def _configure_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 160)

    def _parse(self, text: str) -> ImportBatch:
        return parse_students_csv(text)

    def _add_import_row(self, values: dict[str, str]) -> None:
        from placement_optimizer.application import StudentDraft

        latitude = values.get("latitude", "") or values.get("lat", "")
        longitude = values.get("longitude", "") or values.get("lon", "") or values.get("lng", "")
        coordinates = ", ".join(part for part in (latitude, longitude) if part)
        self._controller.session.add_student(
            StudentDraft(
                key="",
                id=values.get("student_id", "") or values.get("id", ""),
                name=values.get("student_name", "") or values.get("name", ""),
                address=values.get("address", ""),
                coordinates=coordinates,
            )
        )

    def _note_text(self) -> str:
        rows = len(self.model._rows())
        if rows > 100:
            return (
                f"This app is designed for up to 100 students. You can keep going with {rows}, "
                "but finding placements may take longer."
            )
        return ""


class LocationsPage(RosterPage):
    TITLE = "Locations"
    DESCRIPTION = (
        "The places students can go. Type rows, paste from a spreadsheet, or import a CSV."
    )
    ADD_TEXT = "Add location"
    COUNT_SINGULAR = "location"
    COUNT_PLURAL = "locations"
    EMPTY_TITLE = "Add your locations"

    def _make_model(self, controller: SessionController) -> RosterTableModel:
        return LocationsTableModel(controller)

    def _configure_columns(self) -> None:
        header = self.table.horizontalHeader()
        for column in (0, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(5, 130)

    def _parse(self, text: str) -> ImportBatch:
        return parse_locations_csv(text)

    def _add_import_row(self, values: dict[str, str]) -> None:
        from placement_optimizer.application import LocationDraft

        latitude = values.get("latitude", "") or values.get("lat", "")
        longitude = values.get("longitude", "") or values.get("lon", "") or values.get("lng", "")
        coordinates = ", ".join(part for part in (latitude, longitude) if part)
        self._controller.session.add_location(
            LocationDraft(
                key="",
                id=values.get("location_id", "") or values.get("id", ""),
                name=values.get("location_name", "") or values.get("name", ""),
                capacity=values.get("capacity", ""),
                minimum_capacity=values.get("minimum_capacity", "")
                or values.get("min_capacity", ""),
                address=values.get("address", ""),
                coordinates=coordinates,
            )
        )

    def _note_text(self) -> str:
        session = self._controller.session
        students = len(session.students)
        if not students or not session.locations:
            return ""
        capacity = 0
        for row in session.locations:
            try:
                capacity += max(0, int(row.capacity))
            except ValueError:
                continue
        if capacity < students:
            noun = "student" if students == 1 else "students"
            return (
                f"Total capacity is {capacity} for {students} {noun}. "
                "Add spaces so placements can be found for everyone."
            )
        return ""
