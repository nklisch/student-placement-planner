"""Installed/downloadable offline map-pack management dialog."""

from __future__ import annotations

from pathlib import Path

import httpx
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.travel import (
    DEFAULT_PACK_CATALOG_URL,
    GeofabrikRegion,
    InstalledMapPack,
    MapPackCatalog,
    MapPackCatalogEntry,
    MapPackError,
    MapPackStore,
    fetch_geofabrik_regions,
    prepare_geofabrik_region,
)
from placement_optimizer.ui.workers import AsyncOperationWorker


class MapPackDialog(QDialog):
    packActivated = Signal(object)
    operationFinished = Signal()

    def __init__(
        self,
        store: MapPackStore,
        parent: QWidget | None = None,
        *,
        catalog_url: str = DEFAULT_PACK_CATALOG_URL,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._catalog_url = catalog_url
        self._catalog = MapPackCatalog()
        self._regions: tuple[GeofabrikRegion, ...] = ()
        self._worker: AsyncOperationWorker | None = None
        self._operation = ""
        self._close_when_done = False

        self.setWindowTitle("Offline map packs")
        self.setMinimumSize(720, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        intro = QLabel(
            "Download a region once, then addresses and driving times can be calculated "
            "without an internet connection."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("Installed regions"))
        self.installed_list = QListWidget()
        self.installed_list.setAccessibleName("Installed offline map packs")
        self.installed_list.currentRowChanged.connect(lambda _row: self._update_actions())
        layout.addWidget(self.installed_list, stretch=1)

        installed_actions = QHBoxLayout()
        self.activate_button = QPushButton("Use selected region")
        self.activate_button.clicked.connect(self._activate_selected)
        self.verify_button = QPushButton("Check selected pack")
        self.verify_button.clicked.connect(self._verify_selected)
        self.import_button = QPushButton("Install pack file…")
        self.import_button.clicked.connect(self._choose_archive)
        installed_actions.addWidget(self.activate_button)
        installed_actions.addWidget(self.verify_button)
        installed_actions.addWidget(self.import_button)
        installed_actions.addStretch(1)
        layout.addLayout(installed_actions)

        layout.addWidget(QLabel("Ready-made regions (optional)"))
        available_row = QHBoxLayout()
        self.available_combo = QComboBox()
        self.available_combo.setAccessibleName("Downloadable offline map packs")
        self.download_button = QPushButton("Download selected region")
        self.download_button.clicked.connect(self._download_selected)
        self.refresh_button = QPushButton("Refresh list")
        self.refresh_button.clicked.connect(self.refresh_catalog)
        available_row.addWidget(self.available_combo, stretch=1)
        available_row.addWidget(self.download_button)
        available_row.addWidget(self.refresh_button)
        layout.addLayout(available_row)

        layout.addWidget(QLabel("Download directly from OpenStreetMap"))
        direct_help = QLabel(
            "Choose a Geofabrik region. The app downloads the current OpenStreetMap extract "
            "from Geofabrik and prepares it on this computer; this project does not host it."
        )
        direct_help.setWordWrap(True)
        direct_help.setProperty("role", "secondary")
        layout.addWidget(direct_help)
        direct_row = QHBoxLayout()
        self.region_combo = QComboBox()
        self.region_combo.setEditable(True)
        self.region_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.region_combo.lineEdit().setPlaceholderText("Search countries, states, or regions")
        self.region_combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.region_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.region_combo.setAccessibleName("OpenStreetMap regions from Geofabrik")
        self.region_combo.currentIndexChanged.connect(lambda _index: self._update_actions())
        self.region_combo.editTextChanged.connect(lambda _text: self._update_actions())
        self.prepare_region_button = QPushButton("Download and prepare this region")
        self.prepare_region_button.clicked.connect(self._prepare_selected_region)
        self.refresh_regions_button = QPushButton("Refresh OpenStreetMap list")
        self.refresh_regions_button.clicked.connect(self.refresh_source_regions)
        direct_row.addWidget(self.region_combo, stretch=1)
        direct_row.addWidget(self.refresh_regions_button)
        layout.addLayout(direct_row)
        prepare_row = QHBoxLayout()
        prepare_row.addWidget(self.prepare_region_button)
        prepare_row.addStretch(1)
        layout.addLayout(prepare_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("role", "secondary")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        layout.addWidget(self.progress)
        attribution = QLabel(
            'Offline regions use © <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap contributors</a> data under the ODbL."
        )
        attribution.setOpenExternalLinks(True)
        attribution.setProperty("role", "secondary")
        layout.addWidget(attribution)

        bottom = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel download or preparation")
        self.cancel_button.clicked.connect(self._cancel_operation)
        self.cancel_button.hide()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        bottom.addWidget(self.cancel_button)
        bottom.addStretch(1)
        bottom.addWidget(close_button)
        layout.addLayout(bottom)

        self._refresh_installed()
        self._render_catalog()
        self._render_regions()
        QTimer.singleShot(0, self.refresh_source_regions)

    def _refresh_installed(self) -> None:
        active = self._store.active()
        active_path = active.path if active is not None else None
        self.installed_list.clear()
        selected_row = -1
        for row, pack in enumerate(self._store.list_installed()):
            marker = " — in use" if pack.path == active_path else ""
            problem = f" — {pack.problem}" if not pack.compatible else ""
            item = QListWidgetItem(
                f"{pack.manifest.name} ({pack.manifest.version}){marker}{problem}"
            )
            item.setData(Qt.ItemDataRole.UserRole, pack)
            self.installed_list.addItem(item)
            if pack.path == active_path:
                selected_row = row
        if self.installed_list.count():
            self.installed_list.setCurrentRow(max(selected_row, 0))
        else:
            empty = QListWidgetItem("No offline regions installed yet.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.installed_list.addItem(empty)
        self._update_actions()

    def _render_catalog(self) -> None:
        self.available_combo.clear()
        installed = {
            (pack.manifest.pack_id, pack.manifest.version) for pack in self._store.list_installed()
        }
        for entry in self._catalog.packs:
            suffix = " — installed" if (entry.pack_id, entry.version) in installed else ""
            size = _format_size(entry.archive_size)
            self.available_combo.addItem(f"{entry.name} ({size}){suffix}", entry)
        self.download_button.setEnabled(bool(self._catalog.packs) and self._worker is None)

    def _render_regions(self) -> None:
        selected = self._selected_source_region()
        selected_id = selected.region_id if selected is not None else ""
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        selected_index = -1
        for region in self._regions:
            self.region_combo.addItem(region.display_name, region)
            if region.region_id == selected_id:
                selected_index = self.region_combo.count() - 1
        self.region_combo.setCurrentIndex(selected_index)
        if selected_index < 0:
            self.region_combo.setEditText("")
        self.region_combo.blockSignals(False)
        self._update_actions()

    def _selected_source_region(self) -> GeofabrikRegion | None:
        text = self.region_combo.currentText().strip().casefold()
        if not text:
            return None
        exact = [
            region
            for region in self._regions
            if text in {region.display_name.casefold(), region.name.casefold()}
        ]
        return exact[0] if len(exact) == 1 else None

    def refresh_source_regions(self) -> None:
        if self._worker is not None:
            return

        async def fetch(_worker):
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "StudentPlacementPlanner/0.1 "
                        "(+https://github.com/nklisch/student-placement-planner)"
                    )
                },
            ) as client:
                return await fetch_geofabrik_regions(client)

        self._start(
            "source-catalog",
            fetch,
            "Loading the OpenStreetMap region list from Geofabrik…",
            cancellable=False,
        )

    def _prepare_selected_region(self) -> None:
        region = self._selected_source_region()
        if region is None or self._worker is not None:
            return
        answer = QMessageBox.question(
            self,
            "Prepare offline region?",
            f"Download {region.name} directly from Geofabrik and prepare it on this "
            "computer? Larger regions can need several times the download size and may "
            "take a while.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return

        async def prepare(worker):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(None, connect=30),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "StudentPlacementPlanner/0.1 "
                        "(+https://github.com/nklisch/student-placement-planner)"
                    )
                },
            ) as client:
                return await prepare_geofabrik_region(
                    region,
                    self._store,
                    client,
                    progress=worker.report_progress,
                    cancelled=lambda: worker.is_cancel_requested,
                )

        self._start(
            "source-install",
            prepare,
            f"Downloading {region.name} directly from Geofabrik…",
            cancellable=True,
        )

    def refresh_catalog(self) -> None:
        if self._worker is not None:
            return

        async def fetch(_worker):
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                return await self._store.fetch_catalog(client, self._catalog_url)

        self._start("catalog", fetch, "Checking for available regions…", cancellable=False)

    def _download_selected(self) -> None:
        entry = self.available_combo.currentData()
        if not isinstance(entry, MapPackCatalogEntry) or self._worker is not None:
            return

        async def download(worker):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(None, connect=30), follow_redirects=True
            ) as client:
                return await self._store.download_and_install(
                    entry,
                    client,
                    progress=lambda done, total: worker.report_progress(
                        done, total, "Downloading region…"
                    ),
                    cancelled=lambda: worker.is_cancel_requested,
                )

        self._start("install", download, f"Downloading {entry.name}…", cancellable=True)

    def _choose_archive(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Install offline map pack",
            str(Path.home()),
            "Student Placement Planner map packs (*.spp-map-pack);;All files (*)",
        )
        if not path:
            return

        async def install(worker):
            return self._store.install_archive(
                path,
                progress=lambda done, total: worker.report_progress(
                    done, total, "Installing the map pack…"
                ),
                cancelled=lambda: worker.is_cancel_requested,
            )

        self._start("install", install, "Checking and installing the map pack…")

    def _verify_selected(self) -> None:
        pack = self._selected_pack()
        if pack is None:
            return

        async def verify(worker):
            self._store.verify(
                pack,
                deep=True,
                progress=lambda done, total: worker.report_progress(
                    done, total, "Checking the map pack…"
                ),
                cancelled=lambda: worker.is_cancel_requested,
            )
            return pack

        self._start("verify", verify, f"Checking {pack.manifest.name}…")

    def _activate_selected(self) -> None:
        pack = self._selected_pack()
        if pack is None:
            return
        try:
            self._store.activate(pack)
        except MapPackError as error:
            self.status_label.setText(str(error))
            return
        self._refresh_installed()
        self.packActivated.emit(pack)
        self.status_label.setText(f"{pack.manifest.name} is ready to use offline.")

    def _selected_pack(self) -> InstalledMapPack | None:
        item = self.installed_list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, InstalledMapPack) else None

    def _start(self, operation: str, task, status: str, *, cancellable: bool = True) -> None:
        self._operation = operation
        self._worker = AsyncOperationWorker(task, self)
        self._worker.succeeded.connect(self._operation_succeeded)
        self._worker.failed.connect(self._operation_failed)
        self._worker.cancelled_operation.connect(self._operation_cancelled)
        self._worker.progress.connect(self._operation_progress)
        self._worker.finished.connect(self._operation_finished)
        self.status_label.setText(status)
        if operation == "source-install":
            self.prepare_region_button.setText("Downloading and preparing…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setVisible(cancellable)
        self._update_actions()
        self._worker.start()

    def _operation_succeeded(self, result: object) -> None:
        if (
            self._operation == "source-catalog"
            and isinstance(result, tuple)
            and all(isinstance(region, GeofabrikRegion) for region in result)
        ):
            self._regions = result
            self.status_label.setText(
                f"{len(result)} OpenStreetMap regions loaded. Start typing above, choose a "
                "matching region, then select Download and prepare."
            )
        elif self._operation == "catalog" and isinstance(result, MapPackCatalog):
            self._catalog = result
            self.status_label.setText(
                f"{len(result.packs)} region(s) available to download."
                if result.packs
                else (
                    "No ready-made regions are published. Use the direct OpenStreetMap "
                    "option below."
                )
            )
        elif isinstance(result, InstalledMapPack):
            if result.compatible:
                self.status_label.setText(f"{result.manifest.name} is ready to use offline.")
                self.packActivated.emit(result)
            else:
                self.status_label.setText(
                    f"{result.manifest.name} was installed, but {result.problem}"
                )
        self._refresh_installed()
        self._render_catalog()

    def _operation_failed(self, message: str) -> None:
        if self._operation == "catalog" and self._store.list_installed():
            self.status_label.setText(f"{message}. Installed regions are still available offline.")
        else:
            self.status_label.setText(message)

    def _operation_cancelled(self) -> None:
        if self._operation == "source-install":
            self.status_label.setText(
                "Preparation cancelled. A partial download was kept so you can resume later."
            )
        else:
            self.status_label.setText("Download paused. Start it again later to resume.")

    def _operation_progress(self, completed: int, total: int, message: str) -> None:
        self.status_label.setText(message)
        if total <= 0:
            self.progress.setRange(0, 0)
            self.progress.setFormat("")
        else:
            # QProgressBar uses signed 32-bit values, while regional extracts can
            # exceed 2 GB. A fixed scale keeps large downloads observable.
            scale = 1000
            self.progress.setRange(0, scale)
            self.progress.setValue(min(scale, round(completed / total * scale)))
            self.progress.setFormat(f"{_format_size(completed)} of {_format_size(total)}")

    def _operation_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.progress.hide()
        self.cancel_button.hide()
        self.prepare_region_button.setText("Download and prepare this region")
        self.cancel_button.setEnabled(True)
        self._update_actions()
        self._render_catalog()
        self._render_regions()
        self.operationFinished.emit()
        if self._close_when_done:
            self._close_when_done = False
            QTimer.singleShot(0, self.close)

    def _cancel_operation(self) -> None:
        if self._worker is not None:
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Pausing download…")
            self._worker.cancel()

    def cancel_operation(self) -> None:
        self._cancel_operation()

    def has_active_operation(self) -> bool:
        return self._worker is not None

    def _update_actions(self) -> None:
        pack = self._selected_pack()
        idle = self._worker is None
        self.activate_button.setEnabled(idle and pack is not None and pack.compatible)
        self.verify_button.setEnabled(idle and pack is not None)
        self.import_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.download_button.setEnabled(idle and bool(self._catalog.packs))
        self.refresh_regions_button.setEnabled(idle)
        self.prepare_region_button.setEnabled(
            idle and self._selected_source_region() is not None
        )

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._close_when_done = True
            self._worker.cancel()
            event.ignore()
            return
        super().closeEvent(event)


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
