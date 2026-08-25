"""Travel times page: three mode cards and the manual minutes grid.

Manual entry is the fully functional Phase D workflow. The offline map pack
and online Google cards are honest placeholders: they explain what each option
will do in a future release, without fake buttons or hidden provider work.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.application import TravelMode
from placement_optimizer.projects import parse_matrix_csv
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.tablemodels import ManualTimesModel
from placement_optimizer.ui.tableview import PasteTableView
from placement_optimizer.ui.widgets import ModeCard, make_label
from placement_optimizer.ui.workers import CsvImportWorker

if TYPE_CHECKING:
    from placement_optimizer.ui.mainwindow import MainWindow

INTRO = (
    "Driving times decide the placements. Choose how to get them—you can switch "
    "later without losing your students or rules."
)

OFFLINE_COPY = (
    "Download a map of your region once, then it works with no internet. Nothing is sent anywhere."
)
OFFLINE_STATUS = (
    "Offline map packs aren't available in this version yet. When they are, you'll "
    "download your region once and calculate times on this computer. Until then, "
    "enter times yourself."
)

ONLINE_COPY = "Addresses are sent to Google to get driving times. Names and choices are never sent."
ONLINE_DISCLOSURE = (
    "Only street addresses (or coordinates) are sent to Google. Student names, "
    "IDs, choices, and rules never leave this computer."
)
ONLINE_STATUS = (
    "Online maps aren't available in this version yet. Until then, enter times "
    "yourself—the grid works with no internet at all."
)


class TravelPage(QWidget):
    def __init__(self, controller: SessionController, host: MainWindow) -> None:
        super().__init__()
        self._controller = controller
        self._host = host
        self.model = ManualTimesModel(controller)
        self._import_worker: CsvImportWorker | None = None
        self._import_session = None
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

        self.status_label = make_label("", role="secondary")
        layout.addWidget(self.status_label)

        self.panels = QStackedWidget()
        self.panels.addWidget(self._build_manual_panel())
        self.panels.addWidget(self._build_placeholder_panel("Offline map pack", OFFLINE_STATUS))
        online_panel = QWidget()
        online_layout = QVBoxLayout(online_panel)
        online_layout.setContentsMargins(0, 8, 0, 0)
        online_layout.setSpacing(8)
        disclosure = QFrame()
        disclosure.setProperty("banner", "info")
        disclosure_layout = QVBoxLayout(disclosure)
        disclosure_layout.setContentsMargins(12, 8, 12, 8)
        disclosure_layout.addWidget(make_label(ONLINE_DISCLOSURE, wrap=True))
        online_layout.addWidget(disclosure)
        online_layout.addWidget(make_label(ONLINE_STATUS, role="secondary", wrap=True))
        online_layout.addStretch(1)
        self.panels.addWidget(online_panel)
        layout.addWidget(self.panels, stretch=1)

        controller.changed.connect(self.refresh_page)
        controller.session_replaced.connect(self._on_session_replaced)
        self._sync_mode_cards()
        self.refresh_page()

    # --- manual panel ------------------------------------------------------

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

    def _build_placeholder_panel(self, title: str, status: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        frame = QFrame()
        frame.setProperty("card", "true")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(16, 16, 16, 16)
        frame_layout.setSpacing(6)
        frame_layout.addWidget(make_label(title, role="heading"))
        frame_layout.addWidget(make_label(status, role="secondary", wrap=True))
        layout.addWidget(frame)
        layout.addStretch(1)
        return panel

    # --- mode handling ------------------------------------------------------

    def _set_mode(self, mode: TravelMode) -> None:
        self._controller.session.set_travel_mode(mode)
        self._controller.notify()

    def _sync_mode_cards(self) -> None:
        mode = self._controller.session.travel_mode
        # The radios live in separate card frames, so Qt does not treat them as
        # one exclusive group; enforce single-selection here.
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

    # --- refresh -------------------------------------------------------------

    def refresh_page(self) -> None:
        session = self._controller.session
        if session.travel_input_version != self._seen_travel_version:
            # Rosters changed elsewhere: the grid gains/loses rows and columns
            # while unaffected cells keep their values.
            self._seen_travel_version = session.travel_input_version
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
        else:
            self.status_label.setText("")

    # --- clipboard and CSV ----------------------------------------------------

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
            session.set_manual_distance(
                student_key,
                location_key,
                entry.distance_meters,
            )
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
        self._host.import_worker_finished()

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
        self._import_session = None
        self.model.hard_reset()
        self._seen_travel_version = self._controller.session.travel_input_version
        self._sync_mode_cards()
        self.refresh_page()
