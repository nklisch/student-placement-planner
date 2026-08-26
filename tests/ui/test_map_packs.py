from __future__ import annotations

from pathlib import Path

from placement_optimizer.travel import (
    AddressRecord,
    GeofabrikRegion,
    MapPackStore,
    build_map_pack,
    create_address_index,
)
from placement_optimizer.ui.pages import mappacks as mappacks_module
from placement_optimizer.ui.pages.mappacks import MapPackDialog


def _installed_pack(tmp_path: Path):
    tiles = tmp_path / "tiles.tar"
    tiles.write_bytes(b"synthetic tiles")
    addresses = tmp_path / "addresses.sqlite3"
    create_address_index((AddressRecord("1 Test Road", 51.5, -0.12),), addresses)
    archive = tmp_path / "test.spp-map-pack"
    build_map_pack(
        archive,
        pack_id="test-region",
        name="Test Region",
        version="1",
        description="",
        valhalla_version="3.8",
        bounds=(-1, 50, 1, 52),
        tiles=tiles,
        addresses=addresses,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    pack = store.install_archive(archive)
    return store, pack


def test_pack_dialog_uses_installed_pack_when_catalog_is_offline(
    qtbot, tmp_path, monkeypatch
) -> None:
    store, pack = _installed_pack(tmp_path)
    monkeypatch.setattr(MapPackDialog, "refresh_source_regions", lambda _self: None)
    dialog = MapPackDialog(store)
    qtbot.addWidget(dialog)

    assert dialog.installed_list.count() == 1
    assert "Test Region" in dialog.installed_list.item(0).text()
    assert "in use" in dialog.installed_list.item(0).text()
    assert dialog.activate_button.isEnabled()
    assert dialog.available_combo.count() == 0
    assert not dialog.download_button.isEnabled()
    assert store.active() == pack


def test_pack_dialog_prepares_region_directly_from_geofabrik(qtbot, tmp_path, monkeypatch) -> None:
    store, pack = _installed_pack(tmp_path)
    monkeypatch.setattr(MapPackDialog, "refresh_source_regions", lambda _self: None)
    dialog = MapPackDialog(store)
    qtbot.addWidget(dialog)
    region = GeofabrikRegion(
        "andorra",
        "Andorra",
        "europe",
        "https://download.geofabrik.de/europe/andorra-latest.osm.pbf",
    )
    dialog._regions = (region,)
    dialog._render_regions()
    dialog.region_combo.setCurrentIndex(0)

    async def prepare(selected, selected_store, _client, **_kwargs):
        assert selected == region
        assert selected_store is store
        return pack

    monkeypatch.setattr(mappacks_module, "prepare_geofabrik_region", prepare)
    monkeypatch.setattr(
        mappacks_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: mappacks_module.QMessageBox.StandardButton.Yes,
    )
    activated = []
    dialog.packActivated.connect(activated.append)

    dialog._prepare_selected_region()

    qtbot.waitUntil(lambda: dialog._worker is None, timeout=5000)
    assert activated == [pack]
    assert "ready to use offline" in dialog.status_label.text()


def test_typed_region_name_selects_the_download_target(qtbot, tmp_path, monkeypatch) -> None:
    store, _pack = _installed_pack(tmp_path)
    monkeypatch.setattr(MapPackDialog, "refresh_source_regions", lambda _self: None)
    dialog = MapPackDialog(store)
    qtbot.addWidget(dialog)
    andorra = GeofabrikRegion(
        "andorra",
        "Andorra",
        "europe",
        "https://download.geofabrik.de/europe/andorra-latest.osm.pbf",
    )
    albania = GeofabrikRegion(
        "albania",
        "Albania",
        "europe",
        "https://download.geofabrik.de/europe/albania-latest.osm.pbf",
    )
    dialog._regions = (albania, andorra)
    dialog._render_regions()

    dialog.region_combo.setEditText("Andorra")

    assert dialog._selected_source_region() == andorra
    assert dialog.prepare_region_button.isEnabled()

    dialog.region_combo.setEditText("And")
    assert dialog._selected_source_region() is None
    assert not dialog.prepare_region_button.isEnabled()


def test_large_region_progress_uses_a_safe_fixed_scale(qtbot, tmp_path, monkeypatch) -> None:
    store, _pack = _installed_pack(tmp_path)
    monkeypatch.setattr(MapPackDialog, "refresh_source_regions", lambda _self: None)
    dialog = MapPackDialog(store)
    qtbot.addWidget(dialog)

    dialog._operation_progress(3 * 1024**3, 5 * 1024**3, "Downloading…")

    assert dialog.progress.maximum() == 1000
    assert dialog.progress.value() == 600
    assert dialog.progress.format() == "3.0 GB of 5.0 GB"


def test_pack_dialog_disables_incompatible_installed_pack(qtbot, tmp_path, monkeypatch) -> None:
    store, _pack = _installed_pack(tmp_path)
    incompatible = MapPackStore(store.root, runtime_valhalla_version="3.9.0")
    monkeypatch.setattr(MapPackDialog, "refresh_source_regions", lambda _self: None)
    dialog = MapPackDialog(incompatible)
    qtbot.addWidget(dialog)

    assert "needs offline routing 3.8" in dialog.installed_list.item(0).text()
    assert not dialog.activate_button.isEnabled()
    assert dialog.verify_button.isEnabled()
