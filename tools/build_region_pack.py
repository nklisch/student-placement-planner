#!/usr/bin/env python3
"""Build one offline map pack from a regional OpenStreetMap PBF extract.

This is release tooling, not part of the desktop runtime. Install the
``pack-build`` and ``offline-maps`` extras before running it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from placement_optimizer.travel import (
    AddressIndexBuilder,
    AddressRecord,
    build_map_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path, help="Regional .osm.pbf file")
    parser.add_argument("output", type=Path, help="Output .spp-map-pack archive")
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--bounds",
        required=True,
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
    )
    parser.add_argument("--source-updated-at", default="")
    parser.add_argument("--work-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.pbf.is_file():
        raise SystemExit(f"PBF not found: {args.pbf}")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    tiles_dir = work / "valhalla_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    tile_extract = work / "valhalla_tiles.tar"
    tile_extract.touch()

    from valhalla import __version__ as valhalla_version
    from valhalla.config import get_config

    config = get_config(tile_extract=tile_extract, tile_dir=tiles_dir, verbose=False)
    config["mjolnir"]["admin"] = str(work / "admins.sqlite")
    config["mjolnir"]["timezone"] = ""
    config_path = work / "valhalla.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    bin_dir = Path(
        subprocess.check_output(
            [sys.executable, "-m", "valhalla", "print_bin_path"], text=True
        ).strip()
    )
    admin_builder = bin_dir / _executable("valhalla_build_admins")
    tile_builder = bin_dir / _executable("valhalla_build_tiles")
    if admin_builder.is_file():
        subprocess.run(
            [str(admin_builder), "-c", str(config_path), str(args.pbf.resolve())],
            cwd=work,
            check=True,
        )
    subprocess.run(
        [str(tile_builder), "-c", str(config_path), str(args.pbf.resolve())],
        cwd=work,
        check=True,
    )

    tile_extract.unlink(missing_ok=True)
    with tarfile.open(tile_extract, "w") as archive:
        for path in sorted(tiles_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(tiles_dir))

    addresses = work / "addresses.sqlite3"
    count = _build_address_index(args.pbf, addresses)
    if count == 0:
        raise SystemExit("No usable addresses were found in the PBF")

    build_map_pack(
        args.output,
        pack_id=args.pack_id,
        name=args.name,
        version=args.version,
        description=args.description,
        valhalla_version=".".join(valhalla_version.split(".")[:2]),
        bounds=tuple(args.bounds),
        tiles=tile_extract,
        addresses=addresses,
        source_updated_at=args.source_updated_at,
    )
    print(f"Built {args.output} with {count:,} searchable addresses")
    return 0


def _build_address_index(pbf: Path, output: Path) -> int:
    try:
        import osmium
    except ImportError as error:
        raise SystemExit("Install the pack-build extra to extract OSM addresses") from error

    class Handler(osmium.SimpleHandler):
        def __init__(self, builder: AddressIndexBuilder) -> None:
            super().__init__()
            self.builder = builder

        def node(self, node) -> None:
            display = _display_address(node.tags)
            if display and node.location.valid():
                self.builder.add(AddressRecord(display, node.location.lat, node.location.lon))

        def way(self, way) -> None:
            display = _display_address(way.tags)
            if not display:
                return
            coordinates = [(node.lat, node.lon) for node in way.nodes if node.location.valid()]
            if not coordinates:
                return
            latitude = sum(value[0] for value in coordinates) / len(coordinates)
            longitude = sum(value[1] for value in coordinates) / len(coordinates)
            self.builder.add(AddressRecord(display, latitude, longitude))

    with AddressIndexBuilder(output) as builder:
        Handler(builder).apply_file(str(pbf), locations=True, idx="flex_mem")
    return builder.count


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


def _executable(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


if __name__ == "__main__":
    raise SystemExit(main())
