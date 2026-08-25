"""Build the portable map-pack archive format from prepared routing data."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from placement_optimizer.travel.packs import MapPackManifest, PackPayload, file_sha256


def build_map_pack(
    output: str | Path,
    *,
    pack_id: str,
    name: str,
    version: str,
    description: str,
    valhalla_version: str,
    bounds: tuple[float, float, float, float],
    tiles: str | Path,
    addresses: str | Path,
    source_updated_at: str = "",
    created_at: str | None = None,
) -> MapPackManifest:
    """Create one ZIP64 archive ready for catalog publishing or local import."""

    tiles_path = Path(tiles)
    addresses_path = Path(addresses)
    for path in (tiles_path, addresses_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    manifest = MapPackManifest(
        pack_id=pack_id,
        name=name,
        version=version,
        description=description,
        valhalla_version=valhalla_version,
        bounds=bounds,
        created_at=created_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
        source_updated_at=source_updated_at,
        tiles=PackPayload(
            path="valhalla_tiles.tar",
            size=tiles_path.stat().st_size,
            sha256=file_sha256(tiles_path),
        ),
        addresses=PackPayload(
            path="addresses.sqlite3",
            size=addresses_path.stat().st_size,
            sha256=file_sha256(addresses_path),
        ),
    )
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            )
            archive.writestr(
                "NOTICE.txt",
                "Contains information from OpenStreetMap, available under the Open "
                "Database License 1.0.\n"
                "© OpenStreetMap contributors: https://www.openstreetmap.org/copyright\n"
                "License: https://opendatacommons.org/licenses/odbl/1-0/\n",
            )
            archive.write(tiles_path, manifest.tiles.path)
            archive.write(addresses_path, manifest.addresses.path)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest
