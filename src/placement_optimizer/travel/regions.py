"""Direct OpenStreetMap region downloads and local offline-data preparation."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tarfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from placement_optimizer.travel.geocoding import AddressIndexBuilder, AddressRecord
from placement_optimizer.travel.pack_builder import build_map_pack
from placement_optimizer.travel.packs import (
    InstalledMapPack,
    MapPackDownloadCancelled,
    MapPackError,
    MapPackStore,
)

GEOFABRIK_CATALOG_URL = "https://download.geofabrik.de/index-v1-nogeom.json"
RegionProgress = Callable[[int, int, str], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class GeofabrikRegion:
    region_id: str
    name: str
    parent: str
    pbf_url: str

    @property
    def display_name(self) -> str:
        return f"{self.name} — {self.parent}" if self.parent else self.name


async def fetch_geofabrik_regions(
    client: httpx.AsyncClient,
    url: str = GEOFABRIK_CATALOG_URL,
) -> tuple[GeofabrikRegion, ...]:
    try:
        response = await client.get(url)
    except httpx.HTTPError as error:
        raise MapPackError("the OpenStreetMap region list couldn't be reached") from error
    if response.status_code != 200:
        raise MapPackError(f"the OpenStreetMap region list returned HTTP {response.status_code}")
    try:
        payload = response.json()
        features = payload["features"]
    except (KeyError, TypeError, ValueError) as error:
        raise MapPackError("the OpenStreetMap region list contains invalid data") from error
    if not isinstance(features, list):
        raise MapPackError("the OpenStreetMap region list contains invalid data")

    regions: list[GeofabrikRegion] = []
    for feature in features:
        try:
            properties = feature["properties"]
            region_id = str(properties["id"]).strip()
            name = str(properties["name"]).strip()
            parent = str(properties.get("parent", "")).strip()
            pbf_url = str(properties["urls"]["pbf"])
        except (KeyError, TypeError):
            continue
        if not region_id or not name or not _official_geofabrik_url(pbf_url):
            continue
        regions.append(GeofabrikRegion(region_id, name, parent, pbf_url))
    if not regions:
        raise MapPackError("the OpenStreetMap region list contains no usable regions")
    return tuple(
        sorted(regions, key=lambda region: (region.name.casefold(), region.parent.casefold()))
    )


async def prepare_geofabrik_region(
    region: GeofabrikRegion,
    store: MapPackStore,
    client: httpx.AsyncClient,
    *,
    progress: RegionProgress | None = None,
    cancelled: CancellationCheck | None = None,
) -> InstalledMapPack:
    """Download one official extract, build local data, and install it atomically."""

    if not _official_geofabrik_url(region.pbf_url):
        # The remote catalog controls a native PBF parser. Limiting it to the
        # documented Geofabrik HTTPS host prevents catalog data from turning
        # this personal desktop feature into an arbitrary URL fetcher.
        raise MapPackError("the selected region does not use an official Geofabrik download")
    progress = progress or (lambda _done, _total, _message: None)
    cancelled = cancelled or (lambda: False)
    safe_id = re.sub(r"[^a-z0-9-]+", "-", region.region_id.casefold()).strip("-")
    if not safe_id:
        raise MapPackError("the selected region has an invalid identifier")
    work = store.root / ".region-builds" / safe_id
    work.mkdir(parents=True, exist_ok=True)
    pbf = work / "source.osm.pbf"
    try:
        source_updated_at = await _download_extract(
            region.pbf_url,
            pbf,
            client,
            progress=progress,
            cancelled=cancelled,
        )
        _check_cancelled(cancelled)
        progress(0, 0, "Preparing road data on this computer…")
        tiles, bounds, valhalla_version = await _build_routing_data(
            pbf,
            work,
            cancelled=cancelled,
        )
        _check_cancelled(cancelled)
        progress(0, 0, "Preparing the offline address search…")
        addresses = work / "addresses.sqlite3"
        address_task = asyncio.create_task(
            asyncio.to_thread(_build_address_index, pbf, addresses, cancelled)
        )
        try:
            address_count = await asyncio.shield(address_task)
        except asyncio.CancelledError:
            # The parser checks the same cancellation event. Let its thread leave
            # the PBF cleanly before the worker and temporary directory disappear.
            with suppress(MapPackDownloadCancelled):
                await address_task
            raise
        if address_count == 0:
            raise MapPackError("the selected region contains no searchable street addresses")
        _check_cancelled(cancelled)
        progress(0, 0, "Finishing the offline region…")
        archive = work / f"{safe_id}.spp-map-pack"
        version = datetime.now(UTC).strftime("%Y.%m.%d")
        await _to_thread_safely(
            build_map_pack,
            archive,
            pack_id=f"geofabrik-{safe_id}",
            name=region.name,
            version=version,
            description=f"{region.name} roads and addresses downloaded directly from Geofabrik",
            valhalla_version=valhalla_version,
            bounds=bounds,
            tiles=tiles,
            addresses=addresses,
            source_updated_at=source_updated_at,
        )
        _check_cancelled(cancelled)
        installed = await _to_thread_safely(
            store.install_archive,
            archive,
            progress=lambda done, total: progress(done, total, "Installing the offline region…"),
            cancelled=cancelled,
        )
        store.activate(installed)
        shutil.rmtree(work, ignore_errors=True)
        return installed
    except (MapPackDownloadCancelled, asyncio.CancelledError):
        raise
    except MapPackError:
        raise
    except (OSError, ValueError) as error:
        raise MapPackError("the offline region couldn't be prepared on this computer") from error


async def _download_extract(
    url: str,
    target: Path,
    client: httpx.AsyncClient,
    *,
    progress: RegionProgress,
    cancelled: CancellationCheck,
) -> str:
    if target.is_file():
        return datetime.fromtimestamp(target.stat().st_mtime, UTC).isoformat()
    partial = target.with_suffix(f"{target.suffix}.part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    try:
        stream = client.stream("GET", url, headers=headers)
        async with stream as response:
            if response.status_code == 416:
                partial.unlink(missing_ok=True)
                return await _download_extract(
                    url,
                    target,
                    client,
                    progress=progress,
                    cancelled=cancelled,
                )
            if response.status_code not in (200, 206):
                raise MapPackError(
                    f"the OpenStreetMap region download returned HTTP {response.status_code}"
                )
            append = response.status_code == 206 and existing > 0
            if not append:
                existing = 0
            content_length = int(response.headers.get("Content-Length", "0") or 0)
            total = _content_range_total(response.headers.get("Content-Range", ""))
            if total <= 0:
                total = existing + content_length
            mode = "ab" if append else "wb"
            completed = existing
            with partial.open(mode) as output:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    _check_cancelled(cancelled)
                    output.write(chunk)
                    completed += len(chunk)
                    progress(completed, total, f"Downloading {completed / 1024 / 1024:.0f} MB…")
            if total and completed != total:
                raise MapPackError("the OpenStreetMap region download ended early")
            partial.replace(target)
            modified = response.headers.get("Last-Modified", "")
    except MapPackDownloadCancelled:
        raise
    except httpx.HTTPError as error:
        raise MapPackError("the OpenStreetMap region download was interrupted") from error
    if modified:
        try:
            return parsedate_to_datetime(modified).astimezone(UTC).isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC).replace(microsecond=0).isoformat()


async def _build_routing_data(
    pbf: Path,
    work: Path,
    *,
    cancelled: CancellationCheck,
) -> tuple[Path, tuple[float, float, float, float], str]:
    try:
        import valhalla
        from valhalla import __version__ as version
        from valhalla.config import get_config
    except ImportError as error:
        raise MapPackError(
            "offline region preparation is unavailable in this installation"
        ) from error

    tiles_dir = work / "valhalla_tiles"
    shutil.rmtree(tiles_dir, ignore_errors=True)
    tiles_dir.mkdir(parents=True)
    tile_extract = work / "valhalla_tiles.tar"
    tile_extract.touch()
    config = get_config(tile_extract=tile_extract, tile_dir=tiles_dir, verbose=False)
    config["mjolnir"]["admin"] = str(work / "admins.sqlite")
    config["mjolnir"]["timezone"] = ""
    config_path = work / "valhalla.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    bin_dir = Path(valhalla.__file__).resolve().parent / "bin"
    admin_builder = bin_dir / _executable("valhalla_build_admins")
    tile_builder = bin_dir / _executable("valhalla_build_tiles")
    if not tile_builder.is_file():
        raise MapPackError("this installation does not include the offline road-data builder")
    if admin_builder.is_file():
        await _run_builder(admin_builder, config_path, pbf, work, cancelled)
    await _run_builder(tile_builder, config_path, pbf, work, cancelled)
    _check_cancelled(cancelled)

    tile_extract.unlink(missing_ok=True)
    await _to_thread_safely(_write_tile_archive, tiles_dir, tile_extract)
    bounds = await _to_thread_safely(_pbf_bounds, pbf)
    return tile_extract, bounds, ".".join(version.split(".")[:2])


async def _run_builder(
    executable: Path,
    config: Path,
    pbf: Path,
    work: Path,
    cancelled: CancellationCheck,
) -> None:
    _check_cancelled(cancelled)
    log_path = work / f"{executable.name}.log"
    with log_path.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "-c",
            str(config),
            str(pbf),
            cwd=work,
            env=_valhalla_builder_environment(executable),
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            return_code = await process.wait()
        except asyncio.CancelledError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                process.kill()
                await process.wait()
            raise
    if return_code != 0:
        raise MapPackError("the offline road data couldn't be prepared for this region")


def _valhalla_builder_environment(executable: Path) -> dict[str, str] | None:
    if sys.platform != "win32":
        return None
    environment = os.environ.copy()
    package_root = executable.parent.parent.parent
    bundled_libraries = package_root / "pyvalhalla.libs"
    environment["PATH"] = ";".join(
        (str(bundled_libraries), str(package_root), environment.get("PATH", ""))
    )
    return environment


async def _to_thread_safely(function, /, *args, **kwargs):
    """Do not abandon a filesystem-writing thread when its asyncio owner is cancelled."""

    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with suppress(MapPackDownloadCancelled):
            await task
        raise


def _build_address_index(pbf: Path, output: Path, cancelled: CancellationCheck) -> int:
    try:
        import osmium
    except ImportError as error:
        raise MapPackError(
            "offline address preparation is unavailable in this installation"
        ) from error

    class Handler(osmium.SimpleHandler):
        def __init__(self, builder: AddressIndexBuilder) -> None:
            super().__init__()
            self.builder = builder
            self.seen = 0

        def _check(self) -> None:
            self.seen += 1
            if self.seen % 2048 == 0:
                _check_cancelled(cancelled)

        def node(self, node) -> None:
            self._check()
            display = _display_address(node.tags)
            if display and node.location.valid():
                self.builder.add(AddressRecord(display, node.location.lat, node.location.lon))

        def way(self, way) -> None:
            self._check()
            display = _display_address(way.tags)
            if not display:
                return
            coordinates = [(node.lat, node.lon) for node in way.nodes if node.location.valid()]
            if coordinates:
                latitude = sum(value[0] for value in coordinates) / len(coordinates)
                longitude = sum(value[1] for value in coordinates) / len(coordinates)
                self.builder.add(AddressRecord(display, latitude, longitude))

    output.unlink(missing_ok=True)
    with AddressIndexBuilder(output) as builder:
        Handler(builder).apply_file(str(pbf), locations=True, idx="flex_mem")
    _check_cancelled(cancelled)
    return builder.count


def _pbf_bounds(pbf: Path) -> tuple[float, float, float, float]:
    try:
        import osmium

        reader = osmium.io.Reader(str(pbf))
        try:
            box = reader.header().box()
        finally:
            reader.close()
        if not box.valid():
            raise ValueError("PBF has no bounds")
        return (
            box.bottom_left.lon,
            box.bottom_left.lat,
            box.top_right.lon,
            box.top_right.lat,
        )
    except (AttributeError, ImportError, RuntimeError, ValueError) as error:
        raise MapPackError("the downloaded OpenStreetMap region has invalid bounds") from error


def _write_tile_archive(tiles_dir: Path, target: Path) -> None:
    with tarfile.open(target, "w") as archive:
        for path in sorted(tiles_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(tiles_dir))


def _display_address(tags) -> str:
    full = (tags.get("addr:full") or "").strip()
    if full:
        return full
    street = (tags.get("addr:street") or tags.get("addr:place") or "").strip()
    number = (tags.get("addr:housenumber") or "").strip()
    name = (tags.get("name") or "").strip()
    if not street and not name:
        return ""
    first = " ".join(part for part in (number, street) if part) or name
    city = (
        tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or ""
    ).strip()
    postcode = (tags.get("addr:postcode") or "").strip()
    country = (tags.get("addr:country") or "").strip()
    return ", ".join(part for part in (first, city, postcode, country) if part)


def _official_geofabrik_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == "download.geofabrik.de"


def _content_range_total(value: str) -> int:
    match = re.search(r"/(\d+)$", value)
    return int(match.group(1)) if match else 0


def _check_cancelled(cancelled: CancellationCheck) -> None:
    if cancelled():
        raise MapPackDownloadCancelled("region preparation cancelled")


def _executable(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name
