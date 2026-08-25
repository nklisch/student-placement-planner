"""Application shell: navigation rail, stacked pages, footer, menus, project IO."""

from __future__ import annotations

import platform
from dataclasses import replace
from importlib import metadata
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import DraftArea, DraftSession, OutcomeKind, TravelMode
from placement_optimizer.optimization import (
    CHOICES_FIRST_OBJECTIVES,
    FAIR_COMMUTE_OBJECTIVES,
    LOWEST_TOTAL_OBJECTIVES,
)
from placement_optimizer.projects import (
    ProjectFileError,
    export_result_csv,
    load_draft_session,
    save_draft_session,
)
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.dialogs import (
    AboutDialog,
    AdvancedOptionsDialog,
    TroubleshootingDialog,
)
from placement_optimizer.ui.help_content import GOAL_HELP
from placement_optimizer.ui.helpdialogs import GuidedWalkthroughDialog, HelpCenterDialog
from placement_optimizer.ui.pages.results import ResultsPage
from placement_optimizer.ui.pages.roster import LocationsPage, StudentsPage
from placement_optimizer.ui.pages.rules import RulesPage
from placement_optimizer.ui.pages.travel import TravelPage
from placement_optimizer.ui.sample_data import build_sample_session
from placement_optimizer.ui.theme import tokens_for
from placement_optimizer.ui.widgets import Toast, make_label
from placement_optimizer.ui.workers import SolveWorker

STEP_NAMES = ("Students", "Locations", "Rules", "Travel times", "Results")
STEP_HELP = (
    "Enter the students who need placements.",
    "Enter placement locations and how many students each can take.",
    "Add optional choices and placement requirements.",
    "Enter or calculate each student's drive to each location.",
    "Review, export, or print the latest placements.",
)
PROJECT_FILE_SUFFIX = ".spp.json"

_PRESETS = (
    ("Fair commute (recommended)", FAIR_COMMUTE_OBJECTIVES),
    ("Lowest total driving", LOWEST_TOTAL_OBJECTIVES),
    ("Choices first", CHOICES_FIRST_OBJECTIVES),
)
_CUSTOM_LABEL = "Custom"
_MORE_OPTIONS_LABEL = "More options…"


def app_version() -> str:
    try:
        return metadata.version("student-placement-optimizer")
    except metadata.PackageNotFoundError:
        return "0.1.0"


class StepsModel(QAbstractListModel):
    """The five navigation steps with status text refreshed from the session."""

    STATUS_ROLE = Qt.ItemDataRole.UserRole + 1
    ATTENTION_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._statuses = ["○"] * len(STEP_NAMES)
        self._attention = [False] * len(STEP_NAMES)

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(STEP_NAMES)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{index.row() + 1}   {STEP_NAMES[index.row()]}"
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.WhatsThisRole):
            return STEP_HELP[index.row()]
        if role == self.STATUS_ROLE:
            return self._statuses[index.row()]
        if role == self.ATTENTION_ROLE:
            return self._attention[index.row()]
        return None

    def set_status(self, row: int, status: str, attention: bool = False) -> None:
        if self._statuses[row] == status and self._attention[row] == attention:
            return
        self._statuses[row] = status
        self._attention[row] = attention
        changed = self.index(row)
        self.dataChanged.emit(changed, changed)


class StepsRailDelegate(QStyledItemDelegate):
    """Draws the step label on the left and a text status on the right."""

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(40)
        return hint

    def paint(self, painter: QPainter, option, index) -> None:
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style = style_option.widget.style() if style_option.widget else None
        if style is not None:
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_PanelItemViewItem,
                style_option,
                painter,
                style_option.widget,
            )
        tokens = tokens_for(_app())
        rect = style_option.rect.adjusted(12, 0, -12, 0)
        painter.save()
        painter.setPen(style_option.palette.text().color())
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )
        attention = bool(index.data(StepsModel.ATTENTION_ROLE))
        painter.setPen(QColor(tokens["warning"] if attention else tokens["secondary"]))
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            index.data(StepsModel.STATUS_ROLE) or "",
        )
        painter.restore()


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance()


class MainWindow(QMainWindow):
    def __init__(self, controller: SessionController | None = None) -> None:
        super().__init__()
        self.controller = controller or SessionController()
        self._project_path: str | None = None
        self._worker: SolveWorker | None = None
        self._pending_project = None
        self._pending_session: DraftSession | None = None
        self._pending_model_version = -1
        self._is_cancelling = False
        self._close_after_worker = False
        self._close_after_imports = False
        self._last_detail = ""
        self._help_center: HelpCenterDialog | None = None
        self._walkthrough: GuidedWalkthroughDialog | None = None
        self._settings = QSettings("StudentPlacementPlanner", "StudentPlacementPlanner")

        self.setWindowTitle("[*]Untitled placement — Student Placement Planner")
        self.resize(1120, 720)
        self.setMinimumSize(960, 600)

        self._build_central()
        self._build_menus()
        self._build_shortcuts()

        self.toast = Toast(self.centralWidget())
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(750)
        self._progress_timer.timeout.connect(self._show_solve_progress)

        self.controller.changed.connect(self.refresh_chrome)
        self.controller.session_replaced.connect(self._on_session_replaced)

        geometry = self._settings.value("ui/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        self.rail.setCurrentIndex(self.steps_model.index(0))
        self.refresh_chrome()

    # --- construction --------------------------------------------------------

    def _build_central(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(8, 8, 0, 8)
        body.setSpacing(0)

        self.steps_model = StepsModel(self)
        self.rail = QListView()
        self.rail.setObjectName("stepsRail")
        self.rail.setModel(self.steps_model)
        self.rail.setItemDelegate(StepsRailDelegate(self.rail))
        self.rail.setFixedWidth(200)
        self.rail.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.rail.setAccessibleName("Steps")
        self.rail.setAccessibleDescription(
            "Five project steps. Hover a step for a short explanation."
        )
        body.addWidget(self.rail)

        self.stack = QStackedWidget()
        self.pages = [
            StudentsPage(self.controller, self),
            LocationsPage(self.controller, self),
            RulesPage(self.controller, self),
            TravelPage(self.controller, self),
            ResultsPage(self.controller, self),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)

        self.rail.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._step_changed(current.row())
        )

        outer.addWidget(self._build_footer())
        self.setCentralWidget(central)

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setFixedHeight(56)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.readiness_button = QPushButton("")
        self.readiness_button.setToolTip(
            "Shows whether the required inputs are complete. Select it to see what needs attention."
        )
        self.readiness_button.setAccessibleName("Readiness")
        self.readiness_button.clicked.connect(self.show_readiness_menu)
        layout.addWidget(self.readiness_button)

        self.solve_progress = QWidget()
        progress_layout = QHBoxLayout(self.solve_progress)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        self.solve_progress_label = make_label("Finding placements…", role="secondary")
        progress_layout.addWidget(self.solve_progress_label)
        self.solve_progress_bar = QProgressBar()
        self.solve_progress_bar.setRange(0, 0)
        self.solve_progress_bar.setFixedWidth(140)
        self.solve_progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.solve_progress_bar)
        self.cancel_solve_button = QPushButton("Cancel")
        self.cancel_solve_button.setToolTip(
            "Stop this calculation and keep the previous results, if any."
        )
        self.cancel_solve_button.clicked.connect(self.cancel_solve)
        progress_layout.addWidget(self.cancel_solve_button)
        self.solve_progress.hide()
        layout.addWidget(self.solve_progress)

        layout.addStretch(1)

        layout.addWidget(make_label("Goal", role="secondary"))
        self.goal_combo = QComboBox()
        self.goal_combo.setAccessibleName("Placement goal")
        self.goal_combo.setAccessibleDescription(
            "Choose which improvement matters first. The first goal is made as good as "
            "possible before the next begins."
        )
        self.goal_combo.activated.connect(self._goal_activated)
        layout.addWidget(self.goal_combo)

        self.run_button = QPushButton("Find placements")
        self.run_button.setProperty("kind", "primary")
        self.run_button.setObjectName("runButton")
        self.run_button.setToolTip(
            "Find an arrangement using the current students, locations, rules, and driving times."
        )
        self.run_button.clicked.connect(self.find_placements)
        layout.addWidget(self.run_button)
        return footer

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self._add_action(file_menu, "New", self.new_project, QKeySequence.StandardKey.New)
        self._add_action(file_menu, "Open…", self.open_project, QKeySequence.StandardKey.Open)
        self._add_action(file_menu, "Save", self.save, QKeySequence.StandardKey.Save)
        self._add_action(file_menu, "Save As…", self.save_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self.export_action = self._add_action(
            file_menu,
            "Export results…",
            self.export_results,
            self._primary_shortcuts("E"),
        )
        self.print_action = self._add_action(
            file_menu, "Print…", self.print_results, QKeySequence.StandardKey.Print
        )
        file_menu.addSeparator()
        self._add_action(file_menu, "Load sample data", self.load_sample_data)
        file_menu.addSeparator()
        self._add_action(file_menu, "Quit", self.close, QKeySequence.StandardKey.Quit)

        edit_menu = self.menuBar().addMenu("Edit")
        self.undo_action = self._add_action(
            edit_menu, "Undo", self.edit_undo, QKeySequence.StandardKey.Undo
        )
        self.redo_action = self._add_action(
            edit_menu, "Redo", self.edit_redo, QKeySequence.StandardKey.Redo
        )
        edit_menu.addSeparator()
        self.copy_action = self._add_action(
            edit_menu, "Copy", self.edit_copy, QKeySequence.StandardKey.Copy
        )
        self.paste_action = self._add_action(
            edit_menu, "Paste", self.edit_paste, QKeySequence.StandardKey.Paste
        )
        edit_menu.addSeparator()
        self.add_row_action = self._add_action(
            edit_menu,
            "Add row",
            self.edit_add_row,
            self._primary_shortcuts("=", "+"),
        )
        self.delete_rows_action = self._add_action(
            edit_menu,
            "Delete rows",
            self.edit_delete_rows,
            self._primary_shortcuts("-"),
        )

        help_menu = self.menuBar().addMenu("Help")
        self._add_action(
            help_menu,
            "User guide…",
            self.show_user_guide,
            QKeySequence.StandardKey.HelpContents,
        )
        self._add_action(help_menu, "Guided walkthrough…", self.show_guided_walkthrough)
        help_menu.addSeparator()
        self._add_action(help_menu, "Troubleshooting details…", self.show_troubleshooting)
        self._add_action(help_menu, "About", self.show_about)

    def _add_action(self, menu: QMenu, text: str, handler, shortcut=None) -> QAction:
        action = QAction(text, self)
        if isinstance(shortcut, (list, tuple)):
            action.setShortcuts(shortcut)
        elif shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    @staticmethod
    def _primary_shortcuts(*keys: str) -> list[QKeySequence]:
        # Qt maps its portable "Ctrl" modifier to the Command key on macOS.
        return [QKeySequence(f"Ctrl+{key}") for key in keys]

    def _build_shortcuts(self) -> None:
        for step in range(5):
            for sequence in self._primary_shortcuts(str(step + 1)):
                shortcut = QShortcut(sequence, self)
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                shortcut.activated.connect(lambda s=step: self.navigate(s))
        for sequence in self._primary_shortcuts("Return", "Enter"):
            run = QShortcut(sequence, self)
            run.setContext(Qt.ShortcutContext.WindowShortcut)
            run.activated.connect(self.find_placements)

    # --- navigation ----------------------------------------------------------

    def navigate(self, step: int) -> None:
        self.rail.setCurrentIndex(self.steps_model.index(step))

    def _step_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
        self.refresh_edit_actions()

    def current_page(self) -> QWidget:
        return self.pages[self.stack.currentIndex()]

    # --- chrome refresh --------------------------------------------------------

    def refresh_chrome(self) -> None:
        session = self.controller.session
        name = session.name.strip() or "Untitled placement"
        self.setWindowTitle(f"[*]{name} — Student Placement Planner")
        self.setWindowModified(session.is_modified)

        readiness = session.readiness()
        self._update_steps(readiness)
        self._update_footer(readiness)
        self.refresh_edit_actions()
        results_page = self.pages[4]
        self.export_action.setEnabled(results_page.has_usable_result())
        self.print_action.setEnabled(results_page.has_usable_result())

    def _update_steps(self, readiness) -> None:
        session = self.controller.session
        students_issues = self._area_issue_count(readiness, DraftArea.STUDENTS)
        locations_issues = self._area_issue_count(readiness, DraftArea.LOCATIONS)
        travel_issues = self._area_issue_count(readiness, DraftArea.TRAVEL)

        if not session.students:
            self.steps_model.set_status(0, "○")
        elif readiness.students_ready:
            self.steps_model.set_status(0, "✓")
        else:
            self.steps_model.set_status(0, "!", attention=students_issues > 0)

        if not session.locations:
            self.steps_model.set_status(1, "○")
        elif readiness.locations_ready:
            self.steps_model.set_status(1, "✓")
        else:
            self.steps_model.set_status(1, "!", attention=locations_issues > 0)

        self.steps_model.set_status(2, str(self.pages[2].rule_count()))

        if readiness.travel_ready:
            self.steps_model.set_status(3, "✓")
        elif travel_issues:
            self.steps_model.set_status(3, "!", attention=True)
        elif session.manual_times or session.calculated_matrix is not None:
            self.steps_model.set_status(3, "●")
        else:
            self.steps_model.set_status(3, "○")

        results_page = self.pages[4]
        if results_page.outcome is None:
            self.steps_model.set_status(4, "○")
        elif session.results_are_stale:
            self.steps_model.set_status(4, "!", attention=True)
        else:
            self.steps_model.set_status(4, "✓")

    @staticmethod
    def _area_issue_count(readiness, area: DraftArea) -> int:
        return sum(1 for issue in readiness.issues if issue.area is area)

    def _update_footer(self, readiness) -> None:
        session = self.controller.session
        if readiness.ready:
            self.readiness_button.setText("Ready to find placements")
        else:
            missing = sum(
                not value
                for value in (
                    readiness.students_ready,
                    readiness.locations_ready,
                    readiness.travel_ready,
                )
            )
            noun = "step needs" if missing == 1 else "steps need"
            self.readiness_button.setText(f"{missing} {noun} attention")

        stale = session.results_are_stale
        self.run_button.setText("Update placements" if stale else "Find placements")
        self.run_button.setEnabled(self._worker is None)

        self._sync_goal_combo()

    def _sync_goal_combo(self) -> None:
        objectives = self.controller.session.optimization.objectives
        self.goal_combo.blockSignals(True)
        self.goal_combo.clear()
        preset_labels = [label for label, _values in _PRESETS]
        matching = [label for label, values in _PRESETS if values == objectives]
        if not matching:
            self.goal_combo.addItem(_CUSTOM_LABEL)
        self.goal_combo.addItems(preset_labels)
        self.goal_combo.addItem(_MORE_OPTIONS_LABEL)
        self.goal_combo.setCurrentText(matching[0] if matching else _CUSTOM_LABEL)
        self.goal_combo.setToolTip(GOAL_HELP[self.goal_combo.currentText()])
        self.goal_combo.blockSignals(False)

    def _goal_activated(self, index: int) -> None:
        text = self.goal_combo.itemText(index)
        if text == _MORE_OPTIONS_LABEL:
            dialog = AdvancedOptionsDialog(self.controller.session.optimization, self)
            if dialog.exec():
                self.controller.session.set_optimization(dialog.config())
                self.controller.notify()
            self._sync_goal_combo()
            return
        for label, values in _PRESETS:
            if label == text:
                config = self.controller.session.optimization
                self.controller.session.set_optimization(replace(config, objectives=values))
                self.controller.notify()
                return
        self._sync_goal_combo()

    def refresh_edit_actions(self) -> None:
        page = self.current_page()
        stack = self._page_undo_stack(page)
        self.undo_action.setEnabled(bool(stack and stack.can_undo))
        self.redo_action.setEnabled(bool(stack and stack.can_redo))
        table = getattr(page, "table", None)
        self.copy_action.setEnabled(table is not None)
        self.paste_action.setEnabled(table is not None)
        self.add_row_action.setEnabled(hasattr(page, "add_row"))
        self.delete_rows_action.setEnabled(hasattr(page, "delete_selected_rows"))

    def _page_undo_stack(self, page):
        if hasattr(page, "undo"):
            return page.undo
        model = getattr(page, "model", None)
        return getattr(model, "undo", None)

    # --- edit menu routing ------------------------------------------------------

    def edit_undo(self) -> None:
        stack = self._page_undo_stack(self.current_page())
        if stack:
            stack.undo()

    def edit_redo(self) -> None:
        stack = self._page_undo_stack(self.current_page())
        if stack:
            stack.redo()

    def edit_copy(self) -> None:
        table = getattr(self.current_page(), "table", None)
        if table is not None:
            table.copy_selection()

    def edit_paste(self) -> None:
        table = getattr(self.current_page(), "table", None)
        if table is not None:
            table.paste_from_clipboard()

    def edit_add_row(self) -> None:
        page = self.current_page()
        if hasattr(page, "add_row"):
            page.add_row()

    def edit_delete_rows(self) -> None:
        page = self.current_page()
        if hasattr(page, "delete_selected_rows"):
            page.delete_selected_rows()

    # --- readiness menu -----------------------------------------------------------

    def show_readiness_menu(self) -> None:
        session = self.controller.session
        readiness = session.readiness()
        menu = QMenu(self)
        if readiness.ready:
            action = menu.addAction("Everything is ready — run Find placements.")
            action.setEnabled(False)
        else:
            for text, step in self._readiness_actions(readiness):
                menu.addAction(text, lambda s=step: self._jump_to_step(s))
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self.readiness_button.mapToGlobal(self.readiness_button.rect().bottomLeft()))

    def _readiness_actions(self, readiness) -> list[tuple[str, int]]:
        session = self.controller.session
        actions: list[tuple[str, int]] = []
        if not readiness.students_ready:
            if not session.students:
                actions.append(("Students — add your students", 0))
            else:
                count = self._area_issue_count(readiness, DraftArea.STUDENTS)
                actions.append((f"Students — {count} issue(s) need attention", 0))
        if not readiness.locations_ready:
            if not session.locations:
                actions.append(("Locations — add your locations", 1))
            else:
                count = self._area_issue_count(readiness, DraftArea.LOCATIONS)
                actions.append((f"Locations — {count} issue(s) need attention", 1))
        if not readiness.travel_ready:
            if session.travel_mode is TravelMode.MANUAL:
                parts = []
                if readiness.missing_travel_cells:
                    parts.append(f"{readiness.missing_travel_cells} cells empty")
                invalid = self._area_issue_count(readiness, DraftArea.TRAVEL)
                if invalid:
                    parts.append(f"{invalid} need fixing")
                detail = ", ".join(parts) or "incomplete"
                actions.append((f"Travel times — {detail}", 3))
            else:
                actions.append(("Travel times — driving times need to be calculated", 3))
        return actions

    def _jump_to_step(self, step: int) -> None:
        self.navigate(step)
        page = self.pages[step]
        if hasattr(page, "reveal_first_issue"):
            page.reveal_first_issue()

    # --- solving -----------------------------------------------------------------

    def find_placements(self) -> None:
        if self._worker is not None:
            return
        built = self.controller.session.build_project()
        if built.project is None:
            self.show_readiness_menu()
            return
        self._pending_project = built.project
        self._pending_session = self.controller.session
        self._pending_model_version = self.controller.session.model_version
        self._is_cancelling = False
        self._worker = SolveWorker(built.project, self)
        self._worker.finished_outcome.connect(self._on_solve_finished)
        self._worker.finished.connect(self._on_worker_done)
        self._progress_timer.start()
        self._worker.start()
        self.navigate(4)
        self.refresh_chrome()

    def _on_solve_finished(self, outcome) -> None:
        self._progress_timer.stop()
        session = self.controller.session
        if self._pending_session is not session or self._pending_project is None:
            return

        self._last_detail = outcome.message
        results_page = self.pages[4]
        if outcome.kind is OutcomeKind.CANCELLED:
            if results_page.outcome is None:
                results_page.show_outcome(outcome, self._pending_project)
            else:
                self.show_toast("Cancelled. Your previous placements were kept.")
        else:
            session.mark_result(self._pending_model_version)
            results_page.show_outcome(outcome, self._pending_project)
        self.refresh_chrome()

    def _on_worker_done(self) -> None:
        self._progress_timer.stop()
        self.solve_progress.hide()
        self.solve_progress_label.setText("Finding placements…")
        self.cancel_solve_button.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._pending_project = None
        self._pending_session = None
        self._pending_model_version = -1
        self._is_cancelling = False
        should_close = self._close_after_worker
        self._close_after_worker = False
        self.refresh_chrome()
        if should_close:
            QTimer.singleShot(0, self.close)

    def cancel_solve(self) -> None:
        if self._worker is None or self._is_cancelling:
            return
        self._is_cancelling = True
        self._worker.cancel()
        self._progress_timer.stop()
        self.solve_progress_label.setText("Cancelling…")
        self.cancel_solve_button.setEnabled(False)
        self.solve_progress.show()
        self.refresh_chrome()

    def _show_solve_progress(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.solve_progress.show()

    # --- project file actions -------------------------------------------------

    def maybe_close(self) -> bool:
        if not self.controller.session.is_modified:
            return True
        choice = self._confirm_close()
        if choice == "cancel":
            return False
        if choice == "discard":
            return True
        return self.save()

    def _confirm_close(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText("Save changes to this project before closing it?")
        box.setInformativeText("Your unsaved work will be lost if you don't save it.")
        save_button = box.addButton(QMessageBox.StandardButton.Save)
        box.addButton(QMessageBox.StandardButton.Discard)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.standardButton(box.clickedButton())
        if clicked is QMessageBox.StandardButton.Cancel:
            return "cancel"
        if clicked is QMessageBox.StandardButton.Discard:
            return "discard"
        return "save"

    def new_project(self) -> None:
        if self._session_change_blocked():
            return
        if not self.maybe_close():
            return
        self._project_path = None
        self.controller.set_session(DraftSession())
        self.navigate(0)

    def open_project(self) -> None:
        if self._session_change_blocked():
            return
        if not self.maybe_close():
            return
        path = self._ask_open_project(self)
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        if self._session_change_blocked():
            return
        try:
            session = load_draft_session(path)
        except ProjectFileError:
            choice = self._ask_corrupt_project()
            if choice == "new":
                self._project_path = None
                self.controller.set_session(DraftSession())
                self.navigate(0)
            elif choice == "another":
                self.open_project()
            return
        self._project_path = path
        self.controller.set_session(session)
        self.navigate(0)

    def save(self) -> bool:
        if self._project_path is None:
            return self.save_as()
        return self._save_to(self._project_path)

    def save_as(self) -> bool:
        path = self._ask_save_project(self)
        if not path:
            return False
        if not path.endswith(PROJECT_FILE_SUFFIX):
            path += PROJECT_FILE_SUFFIX
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        session = self.controller.session
        try:
            save_draft_session(session, path)
        except ProjectFileError as error:
            QMessageBox.warning(self, "Couldn't save", str(error))
            return False
        self._project_path = path
        session.mark_saved()
        self.show_toast("Project saved.")
        self.refresh_chrome()
        return True

    # --- results export and print ---------------------------------------------

    def export_results(self) -> None:
        results_page = self.pages[4]
        if not results_page.has_usable_result():
            return
        path = self.ask_save_csv(self, "Export results", "placements.csv")
        if not path:
            return
        text = export_result_csv(
            results_page.outcome.result,
            results_page.project.students,
            results_page.project.locations,
        )
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError:
            self.show_toast("The file couldn't be saved. Check the location and try again.")
            return
        self.show_toast("Results exported.")

    def print_results(self) -> None:
        results_page = self.pages[4]
        if not results_page.has_usable_result():
            return
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        outcome = results_page.outcome
        project = results_page.project
        student_names = {student.id: student.name for student in project.students}
        location_names = {location.id: location.name for location in project.locations}
        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                student_names.get(p.student_id, p.student_id),
                (
                    location_names.get(p.location_id or "", "Not placed")
                    if p.location_id
                    else "Not placed"
                ),
                "—" if p.duration_seconds is None else f"{p.duration_seconds / 60:.0f} min",
            )
            for p in outcome.result.placements
        )
        document = QTextDocument()
        document.setHtml(
            f"<h2>{project.name} — Placements</h2>"
            f"<p>{outcome.message}</p>"
            "<table border='0' cellspacing='6'>"
            "<tr><th align='left'>Student</th><th align='left'>Placement</th>"
            "<th align='left'>Drive</th></tr>"
            f"{rows}</table>"
        )
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            document.print_(printer)

    # --- sample data -------------------------------------------------------------

    def load_sample_data(self) -> None:
        if self._session_change_blocked():
            return
        if not self.maybe_close():
            return
        self._project_path = None
        self.controller.set_session(build_sample_session())
        self.navigate(0)
        self.show_toast("Sample data loaded.")

    # --- help -----------------------------------------------------------------

    def show_user_guide(self) -> None:
        if self._help_center is None:
            self._help_center = HelpCenterDialog(self)
        self._help_center.show()
        self._help_center.raise_()
        self._help_center.activateWindow()

    def show_guided_walkthrough(self) -> None:
        if self._walkthrough is None:
            self._walkthrough = GuidedWalkthroughDialog(self.navigate, self)
            self._walkthrough.openUserGuide.connect(self.show_user_guide)
        elif not self._walkthrough.isVisible():
            self._walkthrough.restart()
        self._walkthrough.show()
        self._walkthrough.raise_()
        self._walkthrough.activateWindow()

    def show_troubleshooting(self) -> None:
        mode_names = {
            TravelMode.MANUAL: "Enter times myself",
            TravelMode.OFFLINE: "Offline map pack",
            TravelMode.GOOGLE: "Online maps (Google)",
        }
        dialog = TroubleshootingDialog(
            app_version(),
            platform.platform(),
            mode_names.get(self.controller.session.travel_mode, "Enter times myself"),
            "No offline map pack installed",
            self._last_detail,
            self,
        )
        dialog.exec()

    def show_about(self) -> None:
        AboutDialog(app_version(), self).exec()

    # --- host API used by pages --------------------------------------------------

    def show_toast(self, text: str, action_text: str = "", action=None) -> None:
        self.toast.show_message(text, action_text, action)

    def ask_open_csv(self, parent: QWidget) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getOpenFileName(
            parent, "Import CSV", self._last_directory(), "CSV files (*.csv *.tsv);;All files (*)"
        )
        if path:
            self._remember_directory(path)
            return path
        return None

    def ask_save_csv(self, parent: QWidget, title: str, default_name: str) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getSaveFileName(
            parent,
            title,
            str(Path(self._last_directory()) / default_name),
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self._remember_directory(path)
            return path
        return None

    def report_import(self, accepted: int, kept: int, on_fix, on_discard) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Import finished")
        box.setText(
            f"Imported {accepted} rows. {kept} rows need attention—they're already "
            "in the table, marked for repair."
        )
        fix_button = box.addButton("Fix them in the table", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Discard import", QMessageBox.ButtonRole.DestructiveRole)
        keep_button = box.addButton("Keep as they are", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(fix_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is fix_button:
            on_fix()
        elif clicked is not keep_button:
            on_discard()
            self.show_toast("Import discarded.")

    # --- internal helpers -----------------------------------------------------------

    def _ask_open_project(self, parent: QWidget) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getOpenFileName(
            parent,
            "Open project",
            self._last_directory(),
            f"Placement projects (*{PROJECT_FILE_SUFFIX});;All files (*)",
        )
        if path:
            self._remember_directory(path)
            return path
        return None

    def _ask_save_project(self, parent: QWidget) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getSaveFileName(
            parent,
            "Save project",
            str(
                Path(self._last_directory())
                / f"{self.controller.session.name or 'project'}{PROJECT_FILE_SUFFIX}"
            ),
            f"Placement projects (*{PROJECT_FILE_SUFFIX});;All files (*)",
        )
        if path:
            self._remember_directory(path)
            return path
        return None

    def _ask_corrupt_project(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("Couldn't open project")
        box.setText("This file couldn't be opened—it may be damaged or from another app.")
        new_button = box.addButton("Start a new project", QMessageBox.ButtonRole.AcceptRole)
        another_button = box.addButton("Choose another file…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is new_button:
            return "new"
        if clicked is another_button:
            return "another"
        return "cancel"

    def _confirm_partial_save(self, notes: list[str]) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Save unfinished project?")
        box.setText("This project isn't complete yet.")
        box.setInformativeText(" ".join(notes) + " Save anyway?")
        save_button = box.addButton("Save anyway", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_button)
        box.exec()
        return box.clickedButton() is save_button

    def _last_directory(self) -> str:
        return self._settings.value("ui/lastDirectory", str(Path.home()))

    def _remember_directory(self, path: str) -> None:
        self._settings.setValue("ui/lastDirectory", str(Path(path).parent))

    def _active_import_pages(self) -> list[QWidget]:
        return [
            page
            for page in self.pages
            if hasattr(page, "has_active_import") and page.has_active_import()
        ]

    def import_worker_finished(self) -> None:
        if self._close_after_imports and not self._active_import_pages():
            self._close_after_imports = False
            QTimer.singleShot(0, self.close)

    def _session_change_blocked(self) -> bool:
        if self._worker is not None:
            self.show_toast("Cancel the current calculation and wait for it to finish first.")
            return True
        if self._active_import_pages():
            self.show_toast("Wait for the current import to finish first.")
            return True
        return False

    def _on_session_replaced(self) -> None:
        if self._worker is not None and self._pending_session is not self.controller.session:
            self.cancel_solve()
        self._last_detail = ""
        for page in self.pages:
            stack = self._page_undo_stack(page)
            if stack:
                stack.clear()
        self.refresh_chrome()

    # --- window lifecycle -------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._close_after_worker = True
            self.cancel_solve()
            event.ignore()
            return
        import_pages = self._active_import_pages()
        if import_pages:
            self._close_after_imports = True
            for page in import_pages:
                page.cancel_import()
            event.ignore()
            return
        if self.maybe_close():
            self._settings.setValue("ui/geometry", self.saveGeometry())
            super().closeEvent(event)
        else:
            event.ignore()
