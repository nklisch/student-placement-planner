# Offline map packs

Student Placement Planner can calculate addresses and road driving times without a network connection after a regional map pack has been installed.

## For users

Open **Travel times → Offline map pack → Choose or download a region…**.

The map-pack window can:

- download a published region and resume an interrupted download;
- install a `.spp-map-pack` file received another way;
- keep an older working version when an update fails;
- check installed files for damage;
- explain when a pack needs a different offline-routing version.

Downloading and updating require internet access. Address matching and route calculation do not. A broken or missing pack affects only offline mode; manual entry and Google Maps remain available.

Each pack contains derived OpenStreetMap data. Attribution and the Open Database License notice are included in the pack and shown in the app.

## Pack format

A `.spp-map-pack` is a ZIP64 archive containing:

- `manifest.json` — strict schema/version, region bounds, Valhalla compatibility, file sizes, and SHA-256 checksums;
- `valhalla_tiles.tar` — the regional Valhalla road graph;
- `addresses.sqlite3` — a compact SQLite FTS address index;
- `NOTICE.txt` — OpenStreetMap attribution and ODbL links.

Downloads have a second catalog-level SHA-256 checksum. Installation occurs in a staging directory and becomes active only after validation. Versions use separate directories so a failed replacement cannot destroy the last working pack.

## Building a region

Install the release-only tools:

```bash
python -m pip install '.[offline-maps,pack-build]'
```

Download a regional `.osm.pbf` extract, normally from [Geofabrik](https://download.geofabrik.de/), then run:

```bash
python tools/build_region_pack.py \
  region.osm.pbf region.spp-map-pack \
  --pack-id example-region \
  --name "Example Region" \
  --version 2026.08 \
  --description "Example Region roads and addresses from OpenStreetMap" \
  --bounds WEST SOUTH EAST NORTH \
  --source-updated-at 2026-08 \
  --work-dir build/map-pack
```

The builder uses the pinned pyvalhalla release to create graph tiles and streams OSM addresses into SQLite without retaining the whole region in memory.

The repository workflow **Build offline map pack** provides the same process as a manually dispatched GitHub Actions job.

## Publishing the catalog

After map-pack archives have been attached to a public release or other HTTPS host, create the Pages catalog with:

```bash
python tools/build_pack_catalog.py \
  docs/packs/catalog.json \
  path/to/*.spp-map-pack \
  --base-url https://example.invalid/releases/download/map-packs
```

Commit the catalog only after every URL is publicly downloadable. The desktop app preserves installed regions when the catalog is unavailable.

## Compatibility

Runtime and pack Valhalla major/minor versions must match. The current build pins pyvalhalla 3.8.3 and emits `3.8` packs. Incompatible files remain installed and visible rather than preventing application startup.
