"""Travel-time entry and provider workflows for manual, offline, and Google modes."""

from __future__ import annotations

import csv
import io
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import TravelMode, TravelWorkflow
from placement_optimizer.projects import parse_matrix_csv
from placement_optimizer.travel import (
    InstalledMapPack,
    MapPackStore,
    TravelCoordinateReview,
    TravelMatrix,
)
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.pages.addressreview import AddressReviewDialog
from placement_optimizer.ui.pages.mappacks import MapPackDialog
from placement_optimizer.ui.tablemodels import ManualTimesModel
from placement_optimizer.ui.tableview import PasteTableView
from placement_optimizer.ui.widgets import ModeCard, make_label
from placement_optimizer.ui.workers import AsyncOperationWorker, CsvImportWorker

if TYPE_CHECKING:
    from placement_optimizer.ui.mainwindow import MainWindow

INTRO = (
    "Driving times decide the placements. Choose how to get them—you can switch "
    "later without losing your students or rules."
)
OFFLINE_COPY = (
    "Download a map of your region once, then it works with no internet. Nothing is sent anywhere."
)
ONLINE_COPY = "Addresses are sent to Google to get driving times. Names and choices are never sent."
ONLINE_DISCLOSURE = (
    "Only street addresses (or coordinates) are sent to Google. Student names, "
    "IDs, choices, and rules never leave this computer."
)


class TravelPage(QWidget):
    def __init__(
        self,
        controller: SessionController,
        host: MainWindow,
        *,
        workflow: TravelWorkflow | None = None,
        pack_store: MapPackStore | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._host = host
        self._workflow = workflow or TravelWorkflow()
        self._pack_store = pack_store or MapPackStore()
        self._pack_dialog: MapPackDialog | None = None
        self.model = ManualTimesModel(controller)
        self._import_worker: CsvImportWorker | None = None
        self._import_session = None
        self._provider_worker: AsyncOperationWorker | None = None
        self._provider_session = None
        self._provider_input_version = -1
        self._provider_operation = ""
        self._provider_mode: TravelMode | None = None
        self._provider_result: object | None = None
        self._review: TravelCoordinateReview | None = None
        self._seen_travel_version = controller.session.travel_input_version

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(10)
        layout.addWidget(make_label("Travel times", role="title"))
        layout.addWidget(make_label(INTRO, role="secondary", wrap=True))

        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.manual_card = ModeCard(
            "Enter times myself",
            "Type or paste each home-to-location drive. No internet needed.",
            lambda: self._set_mode(TravelMode.MANUAL),
        )
        self.offline_card = ModeCard(
            "Offline map pack",
            OFFLINE_COPY,
            lambda: self._set_mode(TravelMode.OFFLINE),
        )
        self.online_card = ModeCard(
            "Online maps (Google)",
            ONLINE_COPY,
            lambda: self._set_mode(TravelMode.GOOGLE),
        )
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for button_id, card in enumerate((self.manual_card, self.offline_card, self.online_card)):
            self.mode_group.addButton(card.radio, button_id)
            cards.addWidget(card, stretch=1)
        layout.addLayout(cards)

        self.status_label = make_label("", role="secondary", wrap=True)
        layout.addWidget(self.status_label)
        self.operation_bar = QFrame()
        self.operation_bar.setProperty("banner", "info")
        operation_layout = QHBoxLayout(self.operation_bar)
        operation_layout.setContentsMargins(12, 7, 12, 7)
        self.operation_label = QLabel("Working…")
        self.operation_progress = QProgressBar()
        self.operation_progress.setRange(0, 0)
        self.operation_progress.setTextVisible(False)
        self.operation_progress.setFixedWidth(150)
        self.operation_cancel = QPushButton("Cancel")
        self.operation_cancel.clicked.connect(self.cancel_operation)
        operation_layout.addWidget(self.operation_label)
        operation_layout.addWidget(self.operation_progress)
        operation_layout.addStretch(1)
        operation_layout.addWidget(self.operation_cancel)
        self.operation_bar.hide()
        layout.addWidget(self.operation_bar)

        self.panels = QStackedWidget()
        self.panels.addWidget(self._build_manual_panel())
        self.panels.addWidget(self._build_offline_panel())
        self.panels.addWidget(self._build_online_panel())
        layout.addWidget(self.panels, stretch=1)

        controller.changed.connect(self.refresh_page)
        controller.session_replaced.connect(self._on_session_replaced)
        self._sync_mode_cards()
        self.refresh_page()

    # --- panels ----------------------------------------------------------

    def _build_manual_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        paste_button = QPushButton("Paste")
        paste_button.setToolTip(
            "Paste a block of driving minutes from a spreadsheet at the selected cell."
        )
        paste_button.clicked.connect(self._paste_into_grid)
        self.import_button = QPushButton("Import CSV…")
        self.import_button.setToolTip("Import rows matched by student ID and location ID.")
        self.import_button.clicked.connect(self.import_csv)
        export_button = QPushButton("Export times…")
        export_button.setToolTip("Export the current grid as CSV, including blank cells.")
        export_button.clicked.connect(self.export_csv)
        toolbar.addWidget(paste_button)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(export_button)
        toolbar.addStretch(1)
        self.completeness_label = make_label("", role="secondary")
        toolbar.addWidget(self.completeness_label)
        layout.addLayout(toolbar)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        self.table = PasteTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(110)
        self.table.horizontalHeader().setDefaultSectionSize(140)
        self.table.setToolTip(
            "Enter driving minutes in each cell. Use x or - when no route is possible."
        )
        self.table.setAccessibleName("Driving times table")
        self.table.setAccessibleDescription(
            "Students are rows and locations are columns. Cells contain driving minutes "
            "or x for no route."
        )
        self.table.fileDropped.connect(self.import_csv_path)
        layout.addWidget(self.table, stretch=1)
        self.empty_hint = make_label(
            "Add students and locations first—the grid appears once both exist.",
            role="secondary",
            wrap=True,
        )
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_hint)
        return panel

    def _build_offline_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        card = QFrame()
        card.setProperty("card", "true")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        card_layout.addWidget(make_label("Offline region", role="heading"))
        self.offline_pack_label = make_label("", role="secondary", wrap=True)
        card_layout.addWidget(self.offline_pack_label)
        actions = QHBoxLayout()
        self.manage_packs_button = QPushButton("Choose or download a region…")
        self.manage_packs_button.clicked.connect(self.manage_map_packs)
        self.offline_view_button = QPushButton("View times…")
        self.offline_view_button.clicked.connect(self._view_times)
        self.offline_calculate_button = QPushButton("Review addresses and calculate")
        self.offline_calculate_button.setProperty("kind", "primary")
        self.offline_calculate_button.clicked.connect(
            lambda: self._review_addresses(TravelMode.OFFLINE)
        )
        actions.addWidget(self.manage_packs_button)
        actions.addWidget(self.offline_view_button)
        actions.addWidget(self.offline_calculate_button)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        layout.addWidget(card)
        self.offline_message = make_label("", role="secondary", wrap=True)
        layout.addWidget(self.offline_message)
        layout.addStretch(1)
        return panel

    def _build_online_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        disclosure = QFrame()
        disclosure.setProperty("banner", "info")
        disclosure_layout = QVBoxLayout(disclosure)
        disclosure_layout.setContentsMargins(12, 8, 12, 8)
        disclosure_layout.addWidget(make_label(ONLINE_DISCLOSURE, wrap=True))
        layout.addWidget(disclosure)

        setup = QFrame()
        setup.setProperty("card", "true")
        setup_layout = QVBoxLayout(setup)
        setup_layout.setContentsMargins(16, 14, 16, 14)
        setup_layout.setSpacing(8)
        setup_layout.addWidget(make_label("Google Maps API key", role="heading"))
        key_help = make_label(
            "Enable the Geocoding API and Routes API in your Google Cloud project. "
            "The key is kept in memory only until this app closes.",
            role="secondary",
            wrap=True,
        )
        setup_layout.addWidget(key_help)
        key_row = QHBoxLayout()
        self.google_key = QLineEdit(os.environ.get("GOOGLE_MAPS_API_KEY", ""))
        self.google_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_key.setPlaceholderText("Paste API key")
        self.google_key.setAccessibleName("Google Maps API key")
        show_key = QCheckBox("Show key")
        show_key.toggled.connect(
            lambda shown: self.google_key.setEchoMode(
                QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.google_key, stretch=1)
        key_row.addWidget(show_key)
        setup_layout.addLayout(key_row)
        actions = QHBoxLayout()
        key_help_button = QPushButton("How to get an API key…")
        key_help_button.setProperty("kind", "quiet")
        key_help_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://developers.google.com/maps/documentation/routes/cloud-setup")
            )
        )
        self.google_test_button = QPushButton("Test connection")
        self.google_test_button.clicked.connect(self._test_google)
        self.google_view_button = QPushButton("View times…")
        self.google_view_button.clicked.connect(self._view_times)
        self.google_calculate_button = QPushButton("Review addresses and calculate")
        self.google_calculate_button.setProperty("kind", "primary")
        self.google_calculate_button.clicked.connect(
            lambda: self._review_addresses(TravelMode.GOOGLE)
        )
        actions.addWidget(key_help_button)
        actions.addWidget(self.google_test_button)
        actions.addWidget(self.google_view_button)
        actions.addWidget(self.google_calculate_button)
        actions.addStretch(1)
        setup_layout.addLayout(actions)
        layout.addWidget(setup)
        self.google_message = make_label("", role="secondary", wrap=True)
        layout.addWidget(self.google_message)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        return scroll

    # --- provider operations --------------------------------------------

    def _view_times(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Driving times")
        dialog.setMinimumSize(760, 460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(
            make_label(
                "These are the latest calculated driving minutes. Recalculate after "
                "changing addresses.",
                role="secondary",
                wrap=True,
            )
        )
        table = QTableView()
        table.setModel(ManualTimesModel(self._controller, table))
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setDefaultSectionSize(140)
        table.setAccessibleName("Calculated driving times")
        layout.addWidget(table, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _test_google(self) -> None:
        key = self.google_key.text().strip()
        if not key:
            self.google_message.setText("Paste a Google Maps API key first.")
            return

        async def task(_worker):
            await self._workflow.test_google(key)
            return True

        self._start_provider_operation(
            "google-test",
            TravelMode.GOOGLE,
            task,
            "Testing the Google Maps connection…",
            needs_travel_input=False,
        )

    def _review_addresses(self, mode: TravelMode) -> None:
        travel_input = self._controller.session.build_travel_input()
        if travel_input is None:
            self._host.show_toast("Fix the student and location details first.")
            return
        if mode is TravelMode.GOOGLE:
            key = self.google_key.text().strip()
            if not key:
                self.google_message.setText("Paste a Google Maps API key first.")
                return

            async def task(_worker):
                return await self._workflow.review_google(travel_input, key)

        else:
            pack = self._pack_store.active()
            if pack is None or not pack.compatible:
                self.offline_message.setText(
                    pack.problem
                    if pack is not None
                    else "Choose or download an offline region first."
                )
                return

            async def task(_worker):
                return await self._workflow.review_offline(travel_input, pack)

        self._start_provider_operation(
            "review",
            mode,
            task,
            "Finding the entered addresses…",
            input_version=travel_input.input_version,
        )

    def _calculate_reviewed(self, mode: TravelMode, review: TravelCoordinateReview) -> None:
        if mode is TravelMode.GOOGLE:
            key = self.google_key.text().strip()

            async def task(_worker):
                return await self._workflow.calculate_google(review, key)

        else:
            pack = self._pack_store.active()
            if pack is None:
                self.offline_message.setText("The selected offline region is no longer available.")
                return

            async def task(_worker):
                return await self._workflow.calculate_offline(review, pack)

        self._start_provider_operation(
            "matrix",
            mode,
            task,
            "Calculating driving times…",
            input_version=self._controller.session.travel_input_version,
        )

    def _start_provider_operation(
        self,
        operation: str,
        mode: TravelMode,
        task,
        message: str,
        *,
        input_version: int = -1,
        needs_travel_input: bool = True,
    ) -> None:
        if self._provider_worker is not None:
            return
        self._provider_operation = operation
        self._provider_mode = mode
        self._provider_result = None
        self._provider_session = self._controller.session if needs_travel_input else None
        self._provider_input_version = input_version
        self._provider_worker = AsyncOperationWorker(task, self)
        self._provider_worker.succeeded.connect(self._provider_succeeded)
        self._provider_worker.failed.connect(self._provider_failed)
        self._provider_worker.cancelled_operation.connect(self._provider_cancelled)
        self._provider_worker.finished.connect(self._provider_finished)
        self.operation_label.setText(message)
        self.operation_cancel.setEnabled(True)
        self.operation_bar.show()
        self._set_provider_buttons_enabled(False)
        self._provider_worker.start()

    def _provider_succeeded(self, result: object) -> None:
        self._provider_result = result

    def _handle_provider_success(self, result: object) -> None:
        if self._provider_operation == "google-test":
            self.google_message.setText(
                "Connection successful. Google Geocoding and Routes are ready."
            )
            return
        session = self._controller.session
        if (
            self._provider_session is not session
            or self._provider_mode is not session.travel_mode
            or self._provider_input_version != session.travel_input_version
        ):
            self._message_for_mode(
                self._provider_mode, "Your data changed. Review addresses again."
            )
            return
        if self._provider_operation == "review" and isinstance(result, TravelCoordinateReview):
            dialog = AddressReviewDialog(result, self)
            if dialog.exec():
                self._apply_coordinate_corrections(dialog.corrections())
                self._review = dialog.review()
                mode = self._provider_mode
                if mode is not None:
                    self._calculate_reviewed(mode, self._review)
            return
        if self._provider_operation == "matrix" and isinstance(result, TravelMatrix):
            session.set_calculated_matrix(result)
            self._controller.notify()
            self._message_for_mode(
                self._provider_mode,
                "Driving times are ready. Use Recalculate whenever addresses change.",
            )

    def _apply_coordinate_corrections(self, corrections) -> None:
        if not corrections:
            return
        session = self._controller.session
        student_indexes = {row.id.strip(): index for index, row in enumerate(session.students)}
        location_indexes = {row.id.strip(): index for index, row in enumerate(session.locations)}
        for kind, item_id, coordinate in corrections:
            value = f"{coordinate.latitude:.7f}, {coordinate.longitude:.7f}"
            if kind == "Student" and item_id in student_indexes:
                session.update_student(student_indexes[item_id], coordinates=value)
            elif kind == "Location" and item_id in location_indexes:
                session.update_location(location_indexes[item_id], coordinates=value)
        self._controller.notify()

    def _provider_failed(self, message: str) -> None:
        # Troubleshooting details intentionally exclude roster addresses; the
        # actionable provider message remains visible only on this project page.
        self._host.set_last_detail("A travel provider operation failed; see the Travel times page.")
        self._message_for_mode(
            self._provider_mode,
            f"{message}. Your existing data was kept; try again or choose another travel option.",
        )

    def _provider_cancelled(self) -> None:
        self._message_for_mode(
            self._provider_mode,
            "Cancelled. Your existing travel times were kept.",
        )

    def _provider_finished(self) -> None:
        worker = self._provider_worker
        self._provider_worker = None
        if worker is not None:
            worker.deleteLater()
        self.operation_bar.hide()
        self._set_provider_buttons_enabled(True)
        result = self._provider_result
        self._provider_result = None
        self._host.background_worker_finished()
        if result is not None:
            self._handle_provider_success(result)

    def cancel_operation(self) -> None:
        if self._provider_worker is not None:
            self.operation_label.setText("Cancelling…")
            self.operation_cancel.setEnabled(False)
            self._provider_worker.cancel()
        if self._pack_dialog is not None:
            self._pack_dialog.cancel_operation()

    def has_active_operation(self) -> bool:
        return self._provider_worker is not None or bool(
            self._pack_dialog is not None and self._pack_dialog.has_active_operation()
        )

    def _set_provider_buttons_enabled(self, enabled: bool) -> None:
        self.google_test_button.setEnabled(enabled)
        self.google_calculate_button.setEnabled(enabled)
        self.google_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        self.offline_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        self.offline_calculate_button.setEnabled(enabled and self._pack_store.active() is not None)
        self.manage_packs_button.setEnabled(enabled)

    def _message_for_mode(self, mode: TravelMode | None, message: str) -> None:
        if mode is TravelMode.GOOGLE:
            self.google_message.setText(message)
        elif mode is TravelMode.OFFLINE:
            self.offline_message.setText(message)

    # --- map packs -------------------------------------------------------

    def manage_map_packs(self) -> None:
        if self._pack_dialog is None:
            self._pack_dialog = MapPackDialog(self._pack_store, self)
            self._pack_dialog.packActivated.connect(self._pack_activated)
            self._pack_dialog.operationFinished.connect(self._host.background_worker_finished)
        self._pack_dialog.show()
        self._pack_dialog.raise_()
        self._pack_dialog.activateWindow()

    def _pack_activated(self, pack: InstalledMapPack) -> None:
        self.offline_message.setText(f"{pack.manifest.name} is ready for offline use.")
        self.refresh_page()

    def pack_description(self) -> str:
        pack = self._pack_store.active()
        if pack is None:
            return "No offline map pack selected"
        return f"{pack.manifest.name} {pack.manifest.version}"

    # --- mode and refresh -----------------------------------------------

    def _set_mode(self, mode: TravelMode) -> None:
        if self._provider_worker is not None:
            self.cancel_operation()
        self._controller.session.set_travel_mode(mode)
        self._controller.notify()

    def _sync_mode_cards(self) -> None:
        mode = self._controller.session.travel_mode
        for card, card_mode in (
            (self.manual_card, TravelMode.MANUAL),
            (self.offline_card, TravelMode.OFFLINE),
            (self.online_card, TravelMode.GOOGLE),
        ):
            should_select = mode is card_mode
            if card.radio.isChecked() != should_select:
                card.radio.setChecked(should_select)
        self.panels.setCurrentIndex(
            {TravelMode.MANUAL: 0, TravelMode.OFFLINE: 1, TravelMode.GOOGLE: 2}[mode]
        )

    def refresh_page(self) -> None:
        session = self._controller.session
        if session.travel_input_version != self._seen_travel_version:
            self._seen_travel_version = session.travel_input_version
            self._review = None
            self.model.refresh()
        self._sync_mode_cards()

        readiness = session.readiness()
        filled, total = self.model.completeness()
        self.completeness_label.setText(f"Filled {filled} of {total}" if total else "")
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(filled)
        has_grid = bool(session.students and session.locations)
        self.table.setVisible(has_grid)
        self.empty_hint.setVisible(not has_grid)

        active_pack = self._pack_store.active()
        if active_pack is None:
            self.offline_pack_label.setText("No offline region selected.")
        elif active_pack.compatible:
            self.offline_pack_label.setText(
                f"Using {active_pack.manifest.name} ({active_pack.manifest.version})."
            )
        else:
            self.offline_pack_label.setText(active_pack.problem)
        calculated_ready = (
            session.calculated_matrix is not None and not session.calculated_travel_is_stale
        )
        self.google_calculate_button.setText(
            "Review and recalculate" if calculated_ready else "Review addresses and calculate"
        )
        self.offline_calculate_button.setText(
            "Review and recalculate" if calculated_ready else "Review addresses and calculate"
        )
        if self._provider_worker is None:
            self.offline_calculate_button.setEnabled(
                active_pack is not None and active_pack.compatible
            )
            has_calculated = session.calculated_matrix is not None
            self.offline_view_button.setEnabled(has_calculated)
            self.google_view_button.setEnabled(has_calculated)

        if session.travel_mode is TravelMode.MANUAL:
            if readiness.travel_ready:
                self.status_label.setText(
                    f"Travel times ready — {len(session.students)} students × "  # noqa: RUF001
                    f"{len(session.locations)} locations"
                )
            elif readiness.missing_travel_cells and has_grid:
                self.status_label.setText(
                    f"{readiness.missing_travel_cells} cells still need a number or x."
                )
            else:
                self.status_label.setText("")
        elif session.calculated_matrix is not None and session.calculated_travel_is_stale:
            self.status_label.setText("Needs updating after your latest changes.")
        elif readiness.travel_ready:
            self.status_label.setText(
                f"Travel times ready — {len(session.students)} students × "  # noqa: RUF001
                f"{len(session.locations)} locations"
            )
        else:
            self.status_label.setText("")

    # --- manual clipboard and CSV --------------------------------------

    def _paste_into_grid(self) -> None:
        if not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        self.table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.table.paste_from_clipboard()

    def import_csv(self) -> None:
        path = self._host.ask_open_csv(self)
        if path:
            self.import_csv_path(path)

    def import_csv_path(self, path: str) -> None:
        if self._import_worker is not None:
            self._host.show_toast("An import is already in progress.")
            return
        self._import_session = self._controller.session
        self._import_worker = CsvImportWorker(path, parse_matrix_csv, self)
        self._import_worker.loaded.connect(self._apply_import)
        self._import_worker.failed.connect(self._import_failed)
        self._import_worker.finished.connect(self._import_finished)
        self.import_button.setEnabled(False)
        self.import_button.setText("Importing…")
        self._import_worker.start()

    def _apply_import(self, batch) -> None:
        if self._import_session is not self._controller.session:
            return
        if not batch.items and not batch.draft_rows:
            message = batch.issues[0].message if batch.issues else "No rows were found."
            self._host.show_toast(message)
            return

        session = self._controller.session
        student_keys = {row.id.strip(): row.key for row in session.students}
        location_keys = {row.id.strip(): row.key for row in session.locations}
        self.model.undo.record()
        applied = 0
        unmatched = 0
        for entry in batch.items:
            student_key = student_keys.get(entry.student_id)
            location_key = location_keys.get(entry.location_id)
            if student_key is None or location_key is None:
                unmatched += 1
                continue
            value = "x" if entry.duration_seconds is None else f"{entry.duration_seconds / 60:g}"
            session.set_manual_time(student_key, location_key, value)
            session.set_manual_distance(student_key, location_key, entry.distance_meters)
            applied += 1
        self.model.refresh()
        self._controller.notify()

        problems = unmatched + batch.error_count
        if problems:
            self._host.show_toast(
                f"Filled {applied} cells; {problems} rows didn't match the current "
                "students and locations."
            )
        else:
            self._host.show_toast(f"Filled {applied} cells.")

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
        self._host.background_worker_finished()

    def cancel_import(self) -> None:
        if self._import_worker is not None:
            self._import_worker.cancel()

    def has_active_import(self) -> bool:
        return self._import_worker is not None

    def export_csv(self) -> None:
        session = self._controller.session
        if not session.students or not session.locations:
            self._host.show_toast("Add students and locations first.")
            return
        path = self._host.ask_save_csv(self, "Export driving times", "driving-times.csv")
        if not path:
            return
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["student_id", "location_id", "driving_minutes", "distance_km"])
        for student in session.students:
            for location in session.locations:
                raw = session.manual_times.get((student.key, location.key), "").strip()
                if not raw:
                    continue
                distance = session.manual_distances_meters.get((student.key, location.key))
                writer.writerow(
                    [
                        student.id,
                        location.id,
                        "no route" if raw == "x" else raw,
                        f"{distance / 1000:g}" if distance is not None else "",
                    ]
                )
        try:
            with open(path, "w", encoding="utf-8", newline="") as csv_file:
                csv_file.write(output.getvalue())
        except OSError:
            self._host.show_toast("The file couldn't be saved. Check the location and try again.")
            return
        self._host.show_toast("Driving times exported.")

    def _on_session_replaced(self) -> None:
        self.cancel_import()
        self.cancel_operation()
        self._import_session = None
        self._provider_session = None
        self._review = None
        self.model.hard_reset()
        self._seen_travel_version = self._controller.session.travel_input_version
        self._sync_mode_cards()
        self.refresh_page()
