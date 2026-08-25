"""Downloadable, versioned offline map-pack storage and validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from typing import Literal

import httpx
from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

DEFAULT_PACK_CATALOG_URL = "https://nklisch.github.io/student-placement-planner/packs/catalog.json"
PACK_ARCHIVE_SUFFIX = ".spp-map-pack"


class MapPackError(RuntimeError):
    """A map pack could not be listed, downloaded, installed, or opened."""


class MapPackDownloadCancelled(MapPackError):
    """The partial download is intentionally retained for a later resume."""


class _StrictDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class PackPayload(_StrictDocument):
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def simple_relative_path(self) -> PackPayload:
        path = Path(self.path)
        if path.is_absolute() or len(path.parts) != 1 or path.name != self.path:
            raise ValueError("pack payload paths must be simple file names")
        return self


class MapPackManifest(_StrictDocument):
    schema_version: Literal[1] = 1
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    description: str = Field(default="", max_length=500)
    valhalla_version: str = Field(pattern=r"^\d+\.\d+(?:\.\d+)?$")
    bounds: tuple[float, float, float, float]
    created_at: str = Field(min_length=1)
    source_updated_at: str = Field(default="", max_length=80)
    attribution: str = "© OpenStreetMap contributors"
    source_url: HttpUrl = "https://www.openstreetmap.org"
    data_license: str = "Open Database License 1.0"
    tiles: PackPayload
    addresses: PackPayload

    @model_validator(mode="after")
    def valid_bounds_and_distinct_files(self) -> MapPackManifest:
        _validate_bounds(self.bounds)
        if self.tiles.path == self.addresses.path:
            raise ValueError("tile and address payloads must be different files")
        return self


class MapPackCatalogEntry(_StrictDocument):
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    description: str = Field(default="", max_length=500)
    valhalla_version: str = Field(pattern=r"^\d+\.\d+(?:\.\d+)?$")
    bounds: tuple[float, float, float, float]
    archive_url: HttpUrl
    archive_size: int = Field(gt=0)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid_bounds(self) -> MapPackCatalogEntry:
        _validate_bounds(self.bounds)
        return self


class MapPackCatalog(_StrictDocument):
    schema_version: Literal[1] = 1
    packs: tuple[MapPackCatalogEntry, ...] = ()

    @model_validator(mode="after")
    def unique_versions(self) -> MapPackCatalog:
        keys = [(pack.pack_id, pack.version) for pack in self.packs]
        if len(keys) != len(set(keys)):
            raise ValueError("map-pack catalog entries must be unique")
        return self


@dataclass(frozen=True, slots=True)
class InstalledMapPack:
    manifest: MapPackManifest
    path: Path
    compatible: bool
    problem: str = ""

    @property
    def tiles_path(self) -> Path:
        return self.path / self.manifest.tiles.path

    @property
    def addresses_path(self) -> Path:
        return self.path / self.manifest.addresses.path


ProgressCallback = Callable[[int, int], None]
CancellationCheck = Callable[[], bool]


class MapPackStore:
    """Own versioned packs and an atomic active-pack pointer under user data."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        runtime_valhalla_version: str | None = None,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else user_data_path("Student Placement Planner", "Nathan Klisch") / "map-packs"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._runtime_version = (
            runtime_valhalla_version
            if runtime_valhalla_version is not None
            else _installed_valhalla_version()
        )

    async def fetch_catalog(
        self,
        client: httpx.AsyncClient,
        url: str = DEFAULT_PACK_CATALOG_URL,
    ) -> MapPackCatalog:
        try:
            response = await client.get(url)
        except httpx.HTTPError as error:
            raise MapPackError("the map-pack list couldn't be reached") from error
        if response.status_code != 200:
            raise MapPackError(f"the map-pack list returned HTTP {response.status_code}")
        try:
            return MapPackCatalog.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise MapPackError("the map-pack list contains invalid data") from error

    def list_installed(self) -> tuple[InstalledMapPack, ...]:
        packs: list[InstalledMapPack] = []
        if not self.root.exists():
            return ()
        for manifest_path in sorted(self.root.glob("*/*/manifest.json")):
            try:
                manifest = _read_manifest(manifest_path)
            except MapPackError:
                continue
            pack = self._installed_pack(manifest, manifest_path.parent)
            try:
                self.verify(pack, deep=False)
            except MapPackError as error:
                pack = replace(pack, compatible=False, problem=str(error))
            packs.append(pack)
        return tuple(sorted(packs, key=lambda item: (item.manifest.name, item.manifest.version)))

    def active(self) -> InstalledMapPack | None:
        pointer = self.root / "active.json"
        try:
            value = json.loads(pointer.read_text(encoding="utf-8"))
            pack_id = str(value["pack_id"])
            version = str(value["version"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        manifest_path = self.root / pack_id / version / "manifest.json"
        try:
            manifest = _read_manifest(manifest_path)
            pack = self._installed_pack(manifest, manifest_path.parent)
            self.verify(pack, deep=False)
            return pack
        except MapPackError:
            return None

    def activate(self, pack: InstalledMapPack) -> None:
        self.verify(pack, deep=False)
        if not pack.compatible:
            raise MapPackError(pack.problem)
        _atomic_json(
            self.root / "active.json",
            {"pack_id": pack.manifest.pack_id, "version": pack.manifest.version},
        )

    def verify(
        self,
        pack: InstalledMapPack,
        *,
        deep: bool = True,
        progress: ProgressCallback | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> None:
        completed = 0
        total = pack.manifest.tiles.size + pack.manifest.addresses.size
        for payload in (pack.manifest.tiles, pack.manifest.addresses):
            path = pack.path / payload.path
            try:
                size = path.stat().st_size
            except OSError as error:
                raise MapPackError(f"{pack.manifest.name} is missing {payload.path}") from error
            if size != payload.size:
                raise MapPackError(f"{pack.manifest.name} has an incomplete {payload.path}")
            if deep:
                digest = file_sha256(
                    path,
                    cancelled=cancelled,
                    progress=(
                        (lambda read, base=completed: progress(base + read, total))
                        if progress is not None
                        else None
                    ),
                )
                if digest != payload.sha256:
                    raise MapPackError(f"{pack.manifest.name} has a damaged {payload.path}")
            completed += payload.size

    async def download_and_install(
        self,
        entry: MapPackCatalogEntry,
        client: httpx.AsyncClient,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancellationCheck | None = None,
        activate: bool = True,
    ) -> InstalledMapPack:
        downloads = self.root / ".downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        partial = downloads / f"{entry.pack_id}-{entry.version}{PACK_ARCHIVE_SUFFIX}.part"
        existing = partial.stat().st_size if partial.exists() else 0
        if existing > entry.archive_size:
            partial.unlink(missing_ok=True)
            existing = 0
        if existing == entry.archive_size:
            if file_sha256(partial, cancelled=cancelled) == entry.archive_sha256:
                pack = self.install_archive(
                    partial,
                    activate=activate,
                    progress=progress,
                    cancelled=cancelled,
                )
                partial.unlink(missing_ok=True)
                return pack
            partial.unlink(missing_ok=True)
            existing = 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            async with client.stream("GET", str(entry.archive_url), headers=headers) as response:
                if response.status_code not in (200, 206):
                    raise MapPackError(
                        f"the map-pack download returned HTTP {response.status_code}"
                    )
                append = bool(existing and response.status_code == 206)
                if not append:
                    existing = 0
                mode = "ab" if append else "wb"
                downloaded = existing
                with partial.open(mode) as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if cancelled is not None and cancelled():
                            raise MapPackDownloadCancelled("map-pack download cancelled")
                        output.write(chunk)
                        downloaded += len(chunk)
                        if progress is not None:
                            progress(downloaded, entry.archive_size)
        except MapPackDownloadCancelled:
            raise
        except MapPackError:
            raise
        except (httpx.HTTPError, OSError) as error:
            raise MapPackError("the map pack couldn't be downloaded") from error

        if partial.stat().st_size != entry.archive_size:
            raise MapPackError("the map-pack download is incomplete")
        if file_sha256(partial, cancelled=cancelled) != entry.archive_sha256:
            partial.unlink(missing_ok=True)
            raise MapPackError("the map-pack download did not match its published checksum")
        pack = self.install_archive(
            partial,
            activate=activate,
            progress=progress,
            cancelled=cancelled,
        )
        partial.unlink(missing_ok=True)
        return pack

    def install_archive(
        self,
        archive: str | Path,
        *,
        activate: bool = True,
        progress: ProgressCallback | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> InstalledMapPack:
        source = Path(archive)
        try:
            with zipfile.ZipFile(source) as bundle:
                manifest_bytes = _manifest_bytes(bundle)
                manifest = MapPackManifest.model_validate_json(manifest_bytes)
                staging = self.root / f".install-{manifest.pack_id}-{uuid.uuid4().hex}"
                staging.mkdir(parents=True)
                try:
                    (staging / "manifest.json").write_bytes(manifest_bytes)
                    completed = 0
                    total = manifest.tiles.size + manifest.addresses.size
                    for payload in (manifest.tiles, manifest.addresses):
                        info = bundle.getinfo(payload.path)
                        if info.file_size != payload.size:
                            raise MapPackError(
                                f"{manifest.name} contains an incorrectly sized {payload.path}"
                            )
                        with (
                            bundle.open(info) as input_file,
                            (staging / payload.path).open("wb") as output,
                        ):
                            while chunk := input_file.read(1024 * 1024):
                                if cancelled is not None and cancelled():
                                    raise MapPackDownloadCancelled("map-pack install cancelled")
                                output.write(chunk)
                                completed += len(chunk)
                                if progress is not None:
                                    progress(completed, total)
                    candidate = self._installed_pack(manifest, staging)
                    self.verify(candidate, deep=True, cancelled=cancelled)
                    final = self.root / manifest.pack_id / manifest.version
                    final.parent.mkdir(parents=True, exist_ok=True)
                    backup = final.with_name(f".{final.name}.backup")
                    if backup.exists():
                        shutil.rmtree(backup)
                    if final.exists():
                        final.replace(backup)
                    try:
                        staging.replace(final)
                    except OSError:
                        if backup.exists() and not final.exists():
                            backup.replace(final)
                        raise
                    shutil.rmtree(backup, ignore_errors=True)
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
        except MapPackError:
            raise
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
            raise MapPackError(
                "that file is not a valid Student Placement Planner map pack"
            ) from error

        installed = self._installed_pack(manifest, final)
        if activate and installed.compatible:
            self.activate(installed)
        return installed

    def remove(self, pack: InstalledMapPack) -> None:
        active = self.active()
        if active is not None and active.path == pack.path:
            (self.root / "active.json").unlink(missing_ok=True)
        shutil.rmtree(pack.path, ignore_errors=True)

    def _installed_pack(self, manifest: MapPackManifest, path: Path) -> InstalledMapPack:
        compatible, problem = _compatibility(manifest.valhalla_version, self._runtime_version)
        return InstalledMapPack(manifest, path, compatible, problem)


def _manifest_bytes(bundle: zipfile.ZipFile) -> bytes:
    info = bundle.getinfo("manifest.json")
    # A downloaded/local archive is untrusted input. Capping the small JSON manifest
    # prevents a forged ZIP entry from allocating arbitrary memory before checksums run.
    if info.file_size > 1024 * 1024:
        raise MapPackError("the map-pack manifest is unexpectedly large")
    return bundle.read(info)


def _validate_bounds(bounds: tuple[float, float, float, float]) -> None:
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("pack bounds must be west, south, east, north")


def _read_manifest(path: Path) -> MapPackManifest:
    try:
        return MapPackManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MapPackError("the installed map-pack details couldn't be read") from error


def _compatibility(required: str, runtime: str | None) -> tuple[bool, str]:
    if runtime is None:
        return (
            False,
            "Offline routing isn't included in this build. Reinstall the app with offline maps.",
        )
    required_parts = required.split(".")[:2]
    runtime_parts = runtime.split(".")[:2]
    if required_parts != runtime_parts:
        return (
            False,
            f"This pack needs offline routing {'.'.join(required_parts)}; this app has "
            f"{'.'.join(runtime_parts)}.",
        )
    return True, ""


def _installed_valhalla_version() -> str | None:
    try:
        return metadata.version("pyvalhalla")
    except metadata.PackageNotFoundError:
        return None


def file_sha256(
    path: str | Path,
    *,
    cancelled: CancellationCheck | None = None,
    progress: Callable[[int], None] | None = None,
) -> str:
    digest = hashlib.sha256()
    completed = 0
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            if cancelled is not None and cancelled():
                raise MapPackDownloadCancelled("map-pack operation cancelled")
            digest.update(chunk)
            completed += len(chunk)
            if progress is not None:
                progress(completed)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
