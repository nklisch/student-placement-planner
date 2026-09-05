"""Travel-time entry and online/offline provider workflows."""

from __future__ import annotations

import csv
import io
import os
from dataclasses import replace
from html import escape
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl, Signal
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

from placement_optimizer.application import TravelInput, TravelMode, TravelWorkflow
from placement_optimizer.projects import parse_matrix_csv
from placement_optimizer.travel import (
    InstalledMapPack,
    MapPackStore,
    ResolvedPlace,
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
ONLINE_COPY = "Use a no-key community service, a free openrouteservice account, or Google Maps."
ONLINE_DISCLOSURE = (
    "Online services receive only street addresses (or coordinates). Student names, "
    "IDs, choices, capacities, and rules are never sent."
)
COMMUNITY_COPY = (
    "No account or API key. Uses the shared OpenStreetMap Nominatim and OSRM services "
    "at a respectful rate. Availability is not guaranteed."
)


class TravelPage(QWidget):
    # IDs are for local navigation only, never provider request data.
    addressRepairRequested = Signal(str, str)

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
        self._pack_store_problem = ""
        if pack_store is not None:
            self._pack_store: MapPackStore | None = pack_store
        else:
            try:
                self._pack_store = MapPackStore()
            except OSError:
                self._pack_store = None
                self._pack_store_problem = (
                    "Offline region storage isn't available. Check the app-data folder "
                    "permissions and free space; manual and online travel options still work."
                )
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
        self._review_cache: TravelCoordinateReview | None = None
        self._review_cache_context: tuple[TravelMode | None, str] | None = None
        self._reused_places: dict[tuple[str, str], ResolvedPlace] = {}
        self._address_links: list[tuple[str, str]] = []
        self._seen_travel_version = controller.session.travel_input_version
        self._seen_grid_signature = self._grid_signature()
        self._show_mode_details: bool | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(make_label("Travel times", role="title"))
        heading.addStretch(1)
        self.mode_details_button = QPushButton("About travel options")
        self.mode_details_button.setProperty("kind", "quiet")
        self.mode_details_button.setCheckable(True)
        self.mode_details_button.toggled.connect(self._toggle_mode_details)
        heading.addWidget(self.mode_details_button)
        layout.addLayout(heading)
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
            "Online route services",
            ONLINE_COPY,
            self._select_online_card,
        )
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for button_id, card in enumerate((self.manual_card, self.offline_card, self.online_card)):
            self.mode_group.addButton(card.radio, button_id)
            cards.addWidget(card, stretch=1)
        layout.addLayout(cards)

        self.status_label = make_label("", role="secondary", wrap=True)
        layout.addWidget(self.status_label)
        self.source_label = make_label("", role="secondary", wrap=True)
        layout.addWidget(self.source_label)
        self.address_issues = make_label("", role="secondary", wrap=True)
        self.address_issues.setTextFormat(Qt.TextFormat.RichText)
        self.address_issues.setOpenExternalLinks(False)
        self.address_issues.linkActivated.connect(self._repair_address_link)
        self.address_issues.hide()
        layout.addWidget(self.address_issues)
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
        self.legend = make_label("Minutes · x = no route · blank = not entered", role="secondary")
        layout.addWidget(self.legend)
        self.import_report = make_label("", role="secondary", wrap=True)
        self.import_report.setTextFormat(Qt.TextFormat.PlainText)
        self.import_report_area = QScrollArea()
        self.import_report_area.setWidgetResizable(True)
        self.import_report_area.setMaximumHeight(120)
        self.import_report_area.setWidget(self.import_report)
        self.import_report_area.hide()
        layout.addWidget(self.import_report_area)

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

        community = QFrame()
        community.setProperty("card", "true")
        community_layout = QVBoxLayout(community)
        community_layout.setContentsMargins(16, 14, 16, 14)
        community_layout.setSpacing(8)
        community_layout.addWidget(make_label("Community OpenStreetMap services", role="heading"))
        community_layout.addWidget(make_label(COMMUNITY_COPY, role="secondary", wrap=True))
        community_actions = QHBoxLayout()
        community_policy = QPushButton("Service policy…")
        community_policy.setProperty("kind", "quiet")
        community_policy.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://operations.osmfoundation.org/policies/nominatim/")
            )
        )
        self.community_test_button = QPushButton("Check services")
        self.community_test_button.clicked.connect(self._test_community)
        self.community_view_button = QPushButton("View times…")
        self.community_view_button.clicked.connect(self._view_times)
        self.community_calculate_button = QPushButton("Review addresses and calculate")
        self.community_calculate_button.setProperty("kind", "primary")
        self.community_calculate_button.clicked.connect(
            lambda: self._choose_online_and_review(TravelMode.COMMUNITY)
        )
        community_actions.addWidget(community_policy)
        community_actions.addWidget(self.community_test_button)
        community_actions.addWidget(self.community_view_button)
        community_actions.addWidget(self.community_calculate_button)
        community_actions.addStretch(1)
        community_layout.addLayout(community_actions)
        self.community_message = make_label(
            "Recommended for occasional use.", role="secondary", wrap=True
        )
        community_layout.addWidget(self.community_message)
        layout.addWidget(community)

        ors = QFrame()
        ors.setProperty("card", "true")
        ors_layout = QVBoxLayout(ors)
        ors_layout.setContentsMargins(16, 14, 16, 14)
        ors_layout.setSpacing(8)
        ors_layout.addWidget(make_label("openrouteservice API key", role="heading"))
        ors_layout.addWidget(
            make_label(
                "A free account provides a personal allowance without Google Cloud billing. "
                "The key stays in memory until the app closes.",
                role="secondary",
                wrap=True,
            )
        )
        ors_key_row = QHBoxLayout()
        self.ors_key = QLineEdit(os.environ.get("OPENROUTESERVICE_API_KEY", ""))
        self.ors_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ors_key.setPlaceholderText("Paste openrouteservice API key")
        self.ors_key.setAccessibleName("openrouteservice API key")
        show_ors_key = QCheckBox("Show key")
        show_ors_key.toggled.connect(
            lambda shown: self.ors_key.setEchoMode(
                QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
            )
        )
        ors_key_row.addWidget(self.ors_key, stretch=1)
        ors_key_row.addWidget(show_ors_key)
        ors_layout.addLayout(ors_key_row)
        ors_actions = QHBoxLayout()
        ors_help = QPushButton("Get a free API key…")
        ors_help.setProperty("kind", "quiet")
        ors_help.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://openrouteservice.org/dev/#/signup"))
        )
        self.ors_test_button = QPushButton("Test connection")
        self.ors_test_button.clicked.connect(self._test_openrouteservice)
        self.ors_view_button = QPushButton("View times…")
        self.ors_view_button.clicked.connect(self._view_times)
        self.ors_calculate_button = QPushButton("Review addresses and calculate")
        self.ors_calculate_button.setProperty("kind", "primary")
        self.ors_calculate_button.clicked.connect(
            lambda: self._choose_online_and_review(TravelMode.OPENROUTESERVICE)
        )
        ors_actions.addWidget(ors_help)
        ors_actions.addWidget(self.ors_test_button)
        ors_actions.addWidget(self.ors_view_button)
        ors_actions.addWidget(self.ors_calculate_button)
        ors_actions.addStretch(1)
        ors_layout.addLayout(ors_actions)
        self.ors_message = make_label("", role="secondary", wrap=True)
        ors_layout.addWidget(self.ors_message)
        layout.addWidget(ors)

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
            lambda: self._choose_online_and_review(TravelMode.GOOGLE)
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
                "This grid includes the last calculation and any later manual edits. "
                "Recalculate after changing addresses.\n"
                "Minutes · x = no route · blank = not entered.\n" + self.source_label.text(),
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

    def _test_community(self) -> None:
        async def task(_worker):
            await self._workflow.test_community()
            return True

        self._start_provider_operation(
            "community-test",
            TravelMode.COMMUNITY,
            task,
            "Checking the community services…",
            needs_travel_input=False,
        )

    def _test_openrouteservice(self) -> None:
        key = self.ors_key.text().strip()
        if not key:
            self.ors_message.setText("Paste an openrouteservice API key first.")
            return

        async def task(_worker):
            await self._workflow.test_openrouteservice(key)
            return True

        self._start_provider_operation(
            "ors-test",
            TravelMode.OPENROUTESERVICE,
            task,
            "Testing the openrouteservice connection…",
            needs_travel_input=False,
        )

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
        if self._provider_worker is not None:
            return
        if self._controller.session.travel_mode is not mode:
            self._controller.session.set_travel_mode(mode)
            self._controller.notify()
        travel_input = self._controller.session.build_travel_input()
        if travel_input is None:
            self._host.show_toast("Fix the student and location details first.")
            return
        self._show_address_preflight(travel_input)
        travel_input = self._reuse_review_matches(travel_input, mode)
        if mode is TravelMode.COMMUNITY:

            async def task(_worker):
                return await self._workflow.review_community(travel_input)

        elif mode is TravelMode.OPENROUTESERVICE:
            key = self.ors_key.text().strip()
            if not key:
                self.ors_message.setText("Paste an openrouteservice API key first.")
                return

            async def task(_worker):
                return await self._workflow.review_openrouteservice(travel_input, key)

        elif mode is TravelMode.GOOGLE:
            key = self.google_key.text().strip()
            if not key:
                self.google_message.setText("Paste a Google Maps API key first.")
                return

            async def task(_worker):
                return await self._workflow.review_google(travel_input, key)

        else:
            pack = self._pack_store.active() if self._pack_store is not None else None
            if pack is None or not pack.compatible:
                self.offline_message.setText(
                    pack.problem
                    if pack is not None
                    else self._pack_store_problem or "Choose or download an offline region first."
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

    def _repair_address_link(self, link: str) -> None:
        try:
            kind, item_id = self._address_links[int(link)]
        except (ValueError, IndexError):
            return
        self.addressRepairRequested.emit(kind, item_id)

    def _show_address_preflight(self, travel_input: TravelInput) -> None:
        self._address_links = []
        links = []
        for kind, places in (
            ("Student", travel_input.students),
            ("Location", travel_input.locations),
        ):
            for place in places:
                if place.coordinate is None and not (place.address or "").strip():
                    index = len(self._address_links)
                    self._address_links.append((kind, place.id))
                    links.append(f'<a href="{index}">{escape(kind)}: {escape(place.name)}</a>')
        self.address_issues.setText(
            "Add an address or coordinates: " + "; ".join(links) if links else ""
        )
        self.address_issues.setVisible(bool(links))

    def _review_context(self, mode: TravelMode | None) -> tuple[TravelMode | None, str]:
        pack = (
            self._pack_store.active()
            if mode is TravelMode.OFFLINE and self._pack_store is not None
            else None
        )
        # Display names can collide across regions; cache against the installed pack identity.
        identity = f"{pack.path}:{pack.manifest.addresses.sha256}" if pack is not None else ""
        return mode, identity

    def _reuse_review_matches(self, travel_input: TravelInput, mode: TravelMode) -> TravelInput:
        """Reuse only unchanged address matches; no cache is persisted to disk."""
        self._reused_places = {}
        previous = self._review_cache
        if previous is None or self._review_cache_context != self._review_context(mode):
            return travel_input

        def reuse(kind, places, old_places):
            old_by_id = {place.item_id: place for place in old_places}
            values = []
            for place in places:
                old = old_by_id.get(place.id)
                if (
                    place.coordinate is None
                    and old is not None
                    and old.coordinate is not None
                    and bool(old.entered_address)
                    and not old.coordinate_override
                    and (place.address or "").strip() == old.entered_address
                ):
                    self._reused_places[(kind, place.id)] = old
                    place = replace(place, coordinate=old.coordinate)
                values.append(place)
            return tuple(values)

        return replace(
            travel_input,
            students=reuse("Student", travel_input.students, previous.students),
            locations=reuse("Location", travel_input.locations, previous.locations),
        )

    def _restore_retained_labels(self, review: TravelCoordinateReview) -> TravelCoordinateReview:
        def restore(kind, places):
            return tuple(
                replace(
                    place,
                    matched_address=self._reused_places[(kind, place.item_id)].matched_address,
                    source="Retained address match — unchanged address",
                    coordinate_override=False,
                )
                if (kind, place.item_id) in self._reused_places
                else place
                for place in places
            )

        return TravelCoordinateReview(
            restore("Student", review.students), restore("Location", review.locations)
        )

    def _calculate_reviewed(self, mode: TravelMode, review: TravelCoordinateReview) -> None:
        if mode is TravelMode.COMMUNITY:

            async def task(_worker):
                return await self._workflow.calculate_community(review)

        elif mode is TravelMode.OPENROUTESERVICE:
            key = self.ors_key.text().strip()

            async def task(_worker):
                return await self._workflow.calculate_openrouteservice(review, key)

        elif mode is TravelMode.GOOGLE:
            key = self.google_key.text().strip()

            async def task(_worker):
                return await self._workflow.calculate_google(review, key)

        else:
            pack = self._pack_store.active() if self._pack_store is not None else None
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
        if self._provider_operation == "community-test":
            self.community_message.setText(
                "Services are reachable. Shared capacity can still vary during calculation."
            )
            return
        if self._provider_operation == "ors-test":
            self.ors_message.setText("Connection successful. openrouteservice is ready.")
            return
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
            result = self._restore_retained_labels(result)
            self._review_cache = result
            self._review_cache_context = self._review_context(self._provider_mode)
            dialog = AddressReviewDialog(result, self)
            retry = []
            repair = []
            dialog.retryRequested.connect(lambda: retry.append(True))
            dialog.addressRepairRequested.connect(
                lambda kind, item_id: repair.append((kind, item_id))
            )
            review_mode = self._provider_mode
            review_version = self._provider_input_version
            review_context = self._review_cache_context
            accepted = dialog.exec()
            # Modal dialogs process background import/pack completions too. Never
            # apply a reviewed positional matrix to a roster changed beneath it.
            if (
                session is not self._controller.session
                or review_version != session.travel_input_version
                or review_mode is not session.travel_mode
                or review_context != self._review_context(review_mode)
            ):
                self._message_for_mode(
                    review_mode,
                    "Your data or selected region changed during review. Review addresses again "
                    "before calculating; these coordinate edits were not applied.",
                )
                return
            if accepted:
                self._apply_coordinate_corrections(dialog.corrections())
                self._review = dialog.review()
                mode = self._provider_mode
                if mode is not None:
                    self._calculate_reviewed(mode, self._review)
            elif retry or repair:
                self._review_cache = dialog.review()
                self._apply_coordinate_corrections(dialog.corrections())
                if repair:
                    self.addressRepairRequested.emit(*repair[0])
                elif self._provider_mode is not None:
                    self._review_addresses(self._provider_mode)
            else:
                self._message_for_mode(
                    self._provider_mode,
                    "Address review cancelled. Existing travel times were kept; "
                    "successful matches are available when you retry.",
                )
            return
        if self._provider_operation == "matrix" and isinstance(result, TravelMatrix):
            self._controller.undo.record()
            session.set_calculated_matrix(result)
            self._controller.notify()
            self._message_for_mode(
                self._provider_mode,
                "Driving times are ready. Use Recalculate whenever addresses change.",
            )

    def _apply_coordinate_corrections(self, corrections) -> None:
        if not corrections:
            return
        self._controller.undo.record()
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
        self.community_test_button.setEnabled(enabled)
        self.community_calculate_button.setEnabled(enabled)
        self.community_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        self.ors_test_button.setEnabled(enabled)
        self.ors_calculate_button.setEnabled(enabled)
        self.ors_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        self.google_test_button.setEnabled(enabled)
        self.google_calculate_button.setEnabled(enabled)
        self.google_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        self.offline_view_button.setEnabled(
            enabled and self._controller.session.calculated_matrix is not None
        )
        active_pack = self._pack_store.active() if self._pack_store is not None else None
        self.offline_calculate_button.setEnabled(enabled and active_pack is not None)
        self.manage_packs_button.setEnabled(enabled and self._pack_store is not None)

    def _message_for_mode(self, mode: TravelMode | None, message: str) -> None:
        if mode is TravelMode.COMMUNITY:
            self.community_message.setText(message)
        elif mode is TravelMode.OPENROUTESERVICE:
            self.ors_message.setText(message)
        elif mode is TravelMode.GOOGLE:
            self.google_message.setText(message)
        elif mode is TravelMode.OFFLINE:
            self.offline_message.setText(message)

    # --- map packs -------------------------------------------------------

    def manage_map_packs(self) -> None:
        if self._pack_store is None:
            self.offline_message.setText(self._pack_store_problem)
            return
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
        pack = self._pack_store.active() if self._pack_store is not None else None
        if pack is None:
            return "No offline map pack selected"
        return f"{pack.manifest.name} {pack.manifest.version}"

    # --- mode and refresh -----------------------------------------------

    def _set_mode(self, mode: TravelMode) -> None:
        if self._provider_worker is not None:
            self.cancel_operation()
        self._controller.session.set_travel_mode(mode)
        self._controller.notify()

    def _select_online_card(self) -> None:
        mode = self._controller.session.travel_mode
        if mode not in {
            TravelMode.COMMUNITY,
            TravelMode.OPENROUTESERVICE,
            TravelMode.GOOGLE,
        }:
            mode = TravelMode.COMMUNITY
        self._set_mode(mode)

    def _choose_online_and_review(self, mode: TravelMode) -> None:
        self._set_mode(mode)
        self._review_addresses(mode)

    def _toggle_mode_details(self, checked: bool) -> None:
        self._show_mode_details = checked
        self._sync_mode_cards()

    def _sync_mode_cards(self) -> None:
        session = self._controller.session
        mode = session.travel_mode
        expanded = (
            self._show_mode_details
            if self._show_mode_details is not None
            else not bool(session.active_students and session.active_locations)
        )
        self.mode_details_button.blockSignals(True)
        self.mode_details_button.setChecked(expanded)
        self.mode_details_button.blockSignals(False)
        for card in (self.manual_card, self.offline_card, self.online_card):
            card.description.setVisible(expanded)
        for card, card_modes in (
            (self.manual_card, {TravelMode.MANUAL}),
            (self.offline_card, {TravelMode.OFFLINE}),
            (
                self.online_card,
                {
                    TravelMode.COMMUNITY,
                    TravelMode.OPENROUTESERVICE,
                    TravelMode.GOOGLE,
                },
            ),
        ):
            should_select = mode in card_modes
            if card.radio.isChecked() != should_select:
                card.radio.setChecked(should_select)
        self.panels.setCurrentIndex(
            {
                TravelMode.MANUAL: 0,
                TravelMode.OFFLINE: 1,
                TravelMode.COMMUNITY: 2,
                TravelMode.OPENROUTESERVICE: 2,
                TravelMode.GOOGLE: 2,
            }[mode]
        )

    def _grid_signature(self) -> tuple[tuple[tuple[str, str, str], ...], ...]:
        session = self._controller.session
        return tuple(
            tuple((row.key, row.name, row.id) for row in rows)
            for rows in (session.active_students, session.active_locations)
        )

    def refresh_page(self) -> None:
        session = self._controller.session
        signature = self._grid_signature()
        previous_signature = self._seen_grid_signature
        self._seen_grid_signature = signature
        structure_changed = any(
            tuple(row[0] for row in current) != tuple(row[0] for row in previous)
            for current, previous in zip(signature, previous_signature, strict=True)
        )
        if session.travel_input_version != self._seen_travel_version or structure_changed:
            self._seen_travel_version = session.travel_input_version
            self._review = None
            self.model.refresh()
        else:
            # Names and IDs label the grid but need not invalidate road routes.
            # Header-only updates also preserve the current cell/editor.
            for current, previous, orientation in zip(
                signature,
                previous_signature,
                (Qt.Orientation.Vertical, Qt.Orientation.Horizontal),
                strict=True,
            ):
                if current != previous and current:
                    self.model.headerDataChanged.emit(orientation, 0, len(current) - 1)
        self._sync_mode_cards()

        matrix = session.calculated_matrix
        if matrix is None:
            self.source_label.setText("Source: entered or imported times.")
        else:
            source = {
                "community_osrm": "Community OpenStreetMap services",
                "openrouteservice": "openrouteservice",
                "google_routes": "Google Maps",
            }.get(
                matrix.source,
                "Offline regional map" if matrix.source.startswith("valhalla:") else matrix.source,
            )
            self.source_label.setText(
                f"Source: {source}. "
                + (
                    "Retained from an earlier calculation; needs updating."
                    if session.calculated_travel_is_stale
                    else "Calculated times; later manual edits may also be present."
                )
            )
        readiness = session.readiness()
        filled, total = self.model.completeness()
        self.completeness_label.setText(f"Filled {filled} of {total}" if total else "")
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(filled)
        has_grid = bool(session.active_students and session.active_locations)
        self.table.setVisible(has_grid)
        self.empty_hint.setVisible(not has_grid)

        active_pack = self._pack_store.active() if self._pack_store is not None else None
        if self._pack_store is None:
            self.offline_pack_label.setText(self._pack_store_problem)
        elif active_pack is None:
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
        calculate_text = (
            "Review and recalculate" if calculated_ready else "Review addresses and calculate"
        )
        self.community_calculate_button.setText(calculate_text)
        self.ors_calculate_button.setText(calculate_text)
        self.google_calculate_button.setText(calculate_text)
        self.offline_calculate_button.setText(
            "Review and recalculate" if calculated_ready else "Review addresses and calculate"
        )
        if self._provider_worker is None:
            self.manage_packs_button.setEnabled(self._pack_store is not None)
            self.offline_calculate_button.setEnabled(
                active_pack is not None and active_pack.compatible
            )
            has_calculated = session.calculated_matrix is not None
            self.offline_view_button.setEnabled(has_calculated)
            self.community_view_button.setEnabled(has_calculated)
            self.ors_view_button.setEnabled(has_calculated)
            self.google_view_button.setEnabled(has_calculated)

        if session.travel_mode is TravelMode.MANUAL:
            if readiness.travel_ready:
                self.status_label.setText(
                    f"Travel times ready — {len(session.active_students)} students × "  # noqa: RUF001
                    f"{len(session.active_locations)} locations"
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
                f"Travel times ready — {len(session.active_students)} students × "  # noqa: RUF001
                f"{len(session.active_locations)} locations"
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
        import_session = self._import_session
        self._controller.apply_import(lambda: self._apply_import_now(batch, import_session))

    def _apply_import_now(self, batch, import_session) -> None:
        if import_session is not self._controller.session:
            return
        if not batch.items and not batch.draft_rows:
            message = batch.issues[0].message if batch.issues else "No rows were found."
            self._host.show_toast(message)
            return

        session = self._controller.session
        student_keys = {row.id.strip(): row.key for row in session.active_students}
        location_keys = {row.id.strip(): row.key for row in session.active_locations}
        self.model.undo.record()
        applied = 0
        unmatched = 0
        invalid = 0
        reports = [f"Row {issue.row}: {issue.message}" for issue in batch.issues]
        entries = {(entry.student_id, entry.location_id): entry for entry in batch.items}
        groups: dict[tuple[str, str], list] = {}
        for draft in batch.draft_rows:
            row = draft.as_dict()
            pair = (
                (row.get("student_id") or row.get("student") or "").strip(),
                (row.get("location_id") or row.get("location") or "").strip(),
            )
            groups.setdefault(pair, []).append(draft)
        # Legacy callers may supply parsed entries only; normal imports always
        # use draft rows so failed replacements cannot leave old values ready.
        if not batch.draft_rows:
            groups = {pair: [] for pair in entries}
        bad_rows = {issue.row for issue in batch.issues if issue.level == "error"}
        for pair, drafts in groups.items():
            student_key = student_keys.get(pair[0])
            location_key = location_keys.get(pair[1])
            if student_key is None or location_key is None:
                unmatched += max(len(drafts), 1)
                reports.append(f"Unknown student/location IDs: {pair[0]}, {pair[1]}.")
                continue
            entry = entries.get(pair)
            if len(drafts) > 1 or any(row.row in bad_rows for row in drafts) or entry is None:
                reports.extend(
                    f"Row {row.row} retained input: "
                    + "; ".join(f"{field}={value}" for field, value in row.values)
                    for row in drafts
                )
                raw_values = [self._draft_time_text(row.as_dict()) for row in drafts]
                value = raw_values[0] if raw_values else ""
                if len(drafts) > 1:
                    value = " / ".join(raw_values) + " [duplicate pair — choose one]"
                    reports.append(
                        f"Repeated pair {pair[0]}, {pair[1]}: choose one time in the grid."
                    )
                elif value:
                    # A bad distance beside a valid time must also block readiness.
                    # Preserve simple invalid text verbatim; annotate values that
                    # would otherwise be accepted as a usable time/no-route cell.
                    try:
                        float(value)
                        numeric = True
                    except ValueError:
                        numeric = False
                    if numeric or value.casefold() in {"x", "-", "no route"}:
                        details = "; ".join(
                            f"{field}={text}"
                            for field, text in drafts[0].values
                            if field not in {"student_id", "student", "location_id", "location"}
                        )
                        value += f" [invalid CSV row: {details}]"
                session.set_manual_time(student_key, location_key, value)
                session.set_manual_distance(student_key, location_key, None)
                invalid += 1
            else:
                value = (
                    "x" if entry.duration_seconds is None else f"{entry.duration_seconds / 60:g}"
                )
                session.set_manual_time(student_key, location_key, value)
                session.set_manual_distance(student_key, location_key, entry.distance_meters)
                applied += 1
        self.model.refresh()
        self._controller.notify()
        summary = (
            f"Filled {applied} cells; {invalid} cells marked for repair; "
            f"{unmatched} rows have unknown IDs."
        )
        self.import_report.setText(summary + ("\n" + "\n".join(reports) if reports else ""))
        self.import_report_area.setVisible(bool(reports or invalid or unmatched))
        self._host.show_toast(
            summary if reports or invalid or unmatched else f"Filled {applied} cells."
        )

    @staticmethod
    def _draft_time_text(row: dict[str, str]) -> str:
        for field in ("duration_seconds", "driving_minutes", "duration_minutes", "minutes"):
            if row.get(field, "").strip():
                raw = row[field].strip()
                if field == "duration_seconds":
                    try:
                        seconds = float(raw)
                        if 0 <= seconds <= 1_000_000_000:
                            return f"{seconds / 60:g}"
                    except ValueError:
                        pass
                return raw
        return ""

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
        if not session.active_students or not session.active_locations:
            self._host.show_toast("Add students and locations first.")
            return
        path = self._host.ask_save_csv(self, "Export driving times", "driving-times.csv")
        if not path:
            return
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["student_id", "location_id", "driving_minutes", "distance_km"])
        for student in session.active_students:
            for location in session.active_locations:
                raw = session.manual_times.get((student.key, location.key), "").strip()
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
        self._review_cache = None
        self._review_cache_context = None
        self._reused_places = {}
        self.address_issues.hide()
        self.import_report_area.hide()
        self.model.hard_reset()
        self._seen_travel_version = self._controller.session.travel_input_version
        self._seen_grid_signature = self._grid_signature()
        self._sync_mode_cards()
        self.refresh_page()
