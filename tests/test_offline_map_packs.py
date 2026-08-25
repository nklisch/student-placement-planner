from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import (
    AddressRecord,
    MapPackCatalogEntry,
    MapPackDownloadCancelled,
    MapPackError,
    MapPackStore,
    OfflineAddressIndex,
    TravelDataError,
    ValhallaRouteMatrix,
    build_map_pack,
    create_address_index,
    file_sha256,
)


def _bundle(tmp_path: Path, *, version: str = "2026.01") -> Path:
    tiles = tmp_path / f"tiles-{version}.tar"
    tiles.write_bytes(b"synthetic-valhalla-tiles")
    addresses = tmp_path / f"addresses-{version}.sqlite3"
    create_address_index(
        (
            AddressRecord("10 Example Street, Exampletown AB1 2CD", 51.5, -0.12),
            AddressRecord("North Clinic, 40 Medical Way", 51.52, -0.11),
        ),
        addresses,
    )
    output = tmp_path / f"example-{version}.spp-map-pack"
    build_map_pack(
        output,
        pack_id="example-region",
        name="Example Region",
        version=version,
        description="Small synthetic test region",
        valhalla_version="3.8",
        bounds=(-1.0, 50.0, 1.0, 52.0),
        tiles=tiles,
        addresses=addresses,
        created_at="2026-01-01T00:00:00+00:00",
    )
    return output


async def test_offline_address_index_matches_incomplete_address(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    pack = store.install_archive(bundle)

    result = await OfflineAddressIndex(pack.addresses_path).geocode("10 Example Street AB1")

    assert result.coordinate == Coordinate(51.5, -0.12)
    assert "Exampletown" in result.display_name


async def test_offline_address_index_reports_missing_address(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    pack = store.install_archive(bundle)

    with pytest.raises(TravelDataError, match="not found"):
        await OfflineAddressIndex(pack.addresses_path).geocode("999 Missing Road")


def test_pack_install_activation_and_last_working_version(tmp_path) -> None:
    first_bundle = _bundle(tmp_path, version="2026.01")
    second_bundle = _bundle(tmp_path, version="2026.02")
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")

    first = store.install_archive(first_bundle)
    second = store.install_archive(second_bundle)

    assert store.active() == second
    assert {pack.manifest.version for pack in store.list_installed()} == {
        "2026.01",
        "2026.02",
    }
    store.activate(first)
    assert store.active() == first


def test_damaged_pack_remains_visible_for_repair(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    pack = store.install_archive(bundle)
    pack.tiles_path.write_bytes(b"incomplete")

    damaged = store.list_installed()[0]

    assert not damaged.compatible
    assert "incomplete" in damaged.problem
    assert store.active() is None


def test_incompatible_pack_is_retained_but_cannot_be_activated(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    compatible_store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    compatible_store.install_archive(bundle)
    incompatible_store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.9.0")

    pack = incompatible_store.list_installed()[0]

    assert not pack.compatible
    with pytest.raises(MapPackError, match=r"needs offline routing 3\.8"):
        incompatible_store.activate(pack)


async def test_pack_download_resumes_and_installs(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    body = bundle.read_bytes()
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    downloads = store.root / ".downloads"
    downloads.mkdir(parents=True)
    partial = downloads / "example-region-2026.01.spp-map-pack.part"
    partial.write_bytes(body[:100])
    seen_range: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen_range.append(request.headers.get("Range", ""))
        return httpx.Response(206, content=body[100:])

    entry = MapPackCatalogEntry(
        pack_id="example-region",
        name="Example Region",
        version="2026.01",
        description="",
        valhalla_version="3.8",
        bounds=(-1.0, 50.0, 1.0, 52.0),
        archive_url="https://example.test/pack.spp-map-pack",
        archive_size=len(body),
        archive_sha256=file_sha256(bundle),
    )
    progress: list[tuple[int, int]] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        pack = await store.download_and_install(
            entry,
            client,
            progress=lambda done, total: progress.append((done, total)),
        )

    assert seen_range == ["bytes=100-"]
    assert (len(body), len(body)) in progress
    assert progress[-1][0] == progress[-1][1]
    assert pack.manifest.pack_id == "example-region"
    assert store.active() == pack


async def test_failed_update_keeps_last_working_pack_active(tmp_path) -> None:
    first_bundle = _bundle(tmp_path, version="2026.01")
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    first = store.install_archive(first_bundle)
    damaged = b"not a map pack"
    entry = MapPackCatalogEntry(
        pack_id="example-region",
        name="Example Region",
        version="2026.02",
        description="",
        valhalla_version="3.8",
        bounds=(-1.0, 50.0, 1.0, 52.0),
        archive_url="https://example.test/damaged.spp-map-pack",
        archive_size=len(damaged),
        archive_sha256="0" * 64,
    )

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=damaged)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(MapPackError, match="checksum"):
            await store.download_and_install(entry, client)

    assert store.active() == first


async def test_cancelled_pack_download_keeps_partial_file(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    body = bundle.read_bytes()
    store = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3")
    entry = MapPackCatalogEntry(
        pack_id="example-region",
        name="Example Region",
        version="2026.01",
        description="",
        valhalla_version="3.8",
        bounds=(-1.0, 50.0, 1.0, 52.0),
        archive_url="https://example.test/pack.spp-map-pack",
        archive_size=len(body),
        archive_sha256=file_sha256(bundle),
    )

    downloads = store.root / ".downloads"
    downloads.mkdir(parents=True)
    partial = downloads / "example-region-2026.01.spp-map-pack.part"
    partial.write_bytes(body[:20])

    async def stream(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=20-"
        return httpx.Response(206, content=body[20:])

    async with httpx.AsyncClient(transport=httpx.MockTransport(stream)) as client:
        with pytest.raises(MapPackDownloadCancelled):
            await store.download_and_install(entry, client, cancelled=lambda: True)

    partials = list((store.root / ".downloads").glob("*.part"))
    assert partials and partials[0].stat().st_size > 0


def test_valhalla_adapter_parses_concise_matrix_with_network_blocked(tmp_path, monkeypatch) -> None:
    import socket

    def block_network(*_args, **_kwargs):
        raise AssertionError("offline calculation attempted network access")

    monkeypatch.setattr(socket, "create_connection", block_network)
    bundle = _bundle(tmp_path)
    pack = MapPackStore(tmp_path / "store", runtime_valhalla_version="3.8.3").install_archive(
        bundle
    )

    class Actor:
        def matrix(self, request):
            assert request["costing"] == "auto"
            return {
                "sources_to_targets": {
                    "distances": [[1.25, None]],
                    "durations": [[180.4, None]],
                }
            }

    async def run():
        router = ValhallaRouteMatrix(
            pack,
            actor_factory=lambda _config: Actor(),
            config_factory=lambda **_kwargs: {},
        )
        return await router.route_matrix(
            (Coordinate(51.5, -0.12),),
            (Coordinate(51.52, -0.11), Coordinate(51.6, -0.2)),
        )

    import asyncio

    matrix = asyncio.run(run())
    assert matrix.distances_meters == ((1250, None),)
    assert matrix.durations_seconds == ((180, None),)
    assert matrix.source == "valhalla:example-region:2026.01"
