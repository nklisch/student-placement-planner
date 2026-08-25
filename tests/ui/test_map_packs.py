from __future__ import annotations

from pathlib import Path

from placement_optimizer.travel import (
    AddressRecord,
    MapPackStore,
    build_map_pack,
    create_address_index,
)
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
    monkeypatch.setattr(MapPackDialog, "refresh_catalog", lambda _self: None)
    dialog = MapPackDialog(store)
    qtbot.addWidget(dialog)

    assert dialog.installed_list.count() == 1
    assert "Test Region" in dialog.installed_list.item(0).text()
    assert "in use" in dialog.installed_list.item(0).text()
    assert dialog.activate_button.isEnabled()
    assert dialog.available_combo.count() == 0
    assert not dialog.download_button.isEnabled()
    assert store.active() == pack


def test_pack_dialog_disables_incompatible_installed_pack(qtbot, tmp_path, monkeypatch) -> None:
    store, _pack = _installed_pack(tmp_path)
    incompatible = MapPackStore(store.root, runtime_valhalla_version="3.9.0")
    monkeypatch.setattr(MapPackDialog, "refresh_catalog", lambda _self: None)
    dialog = MapPackDialog(incompatible)
    qtbot.addWidget(dialog)

    assert "needs offline routing 3.8" in dialog.installed_list.item(0).text()
    assert not dialog.activate_button.isEnabled()
    assert dialog.verify_button.isEnabled()
