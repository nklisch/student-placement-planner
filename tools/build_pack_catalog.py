#!/usr/bin/env python3
"""Create the GitHub Pages catalog for published .spp-map-pack archives."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

from placement_optimizer.travel import MapPackManifest, file_sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("archives", type=Path, nargs="+")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Public URL directory containing the archives",
    )
    args = parser.parse_args()

    entries = []
    for archive_path in args.archives:
        with zipfile.ZipFile(archive_path) as archive:
            manifest = MapPackManifest.model_validate_json(archive.read("manifest.json"))
        entries.append(
            {
                "pack_id": manifest.pack_id,
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "valhalla_version": manifest.valhalla_version,
                "bounds": manifest.bounds,
                "archive_url": f"{args.base_url.rstrip('/')}/{quote(archive_path.name)}",
                "archive_size": archive_path.stat().st_size,
                "archive_sha256": file_sha256(archive_path),
            }
        )
    payload = {
        "schema_version": 1,
        "packs": sorted(entries, key=lambda entry: (entry["name"], entry["version"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
