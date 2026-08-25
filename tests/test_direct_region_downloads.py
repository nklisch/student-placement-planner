from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from placement_optimizer.travel import GeofabrikRegion, fetch_geofabrik_regions, regions
from placement_optimizer.travel.packs import MapPackDownloadCancelled
from placement_optimizer.travel.regions import _download_extract

pytestmark = pytest.mark.asyncio


async def test_windows_builder_can_find_packaged_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "site-packages" / "valhalla" / "bin" / "builder.exe"
    monkeypatch.setattr(regions.sys, "platform", "win32")
    monkeypatch.setenv("PATH", "original-path")

    environment = regions._valhalla_builder_environment(executable)

    assert environment is not None
    assert environment["PATH"].split(";") == [
        str(tmp_path / "site-packages" / "pyvalhalla.libs"),
        str(tmp_path / "site-packages"),
        "original-path",
    ]


async def test_geofabrik_catalog_keeps_only_official_downloads() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "properties": {
                            "id": "andorra",
                            "name": "Andorra",
                            "parent": "europe",
                            "urls": {
                                "pbf": "https://download.geofabrik.de/europe/andorra-latest.osm.pbf"
                            },
                        }
                    },
                    {
                        "properties": {
                            "id": "unsafe",
                            "name": "Unsafe",
                            "urls": {"pbf": "https://example.invalid/map.osm.pbf"},
                        }
                    },
                    {"properties": {"id": "incomplete"}},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        regions = await fetch_geofabrik_regions(client, "https://catalog.test")

    assert regions == (
        GeofabrikRegion(
            "andorra",
            "Andorra",
            "europe",
            "https://download.geofabrik.de/europe/andorra-latest.osm.pbf",
        ),
    )
    assert regions[0].display_name == "Andorra — europe"


async def test_extract_download_resumes_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "region.osm.pbf"
    partial = target.with_suffix(".pbf.part")
    partial.write_bytes(b"first-")
    seen_range = ""
    progress: list[tuple[int, int]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal seen_range
        seen_range = request.headers.get("Range", "")
        return httpx.Response(
            206,
            headers={
                "Content-Range": "bytes 6-11/12",
                "Last-Modified": "Tue, 25 Aug 2026 00:00:00 GMT",
            },
            content=b"second",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        updated = await _download_extract(
            "https://download.geofabrik.de/test.osm.pbf",
            target,
            client,
            progress=lambda done, total, _message: progress.append((done, total)),
            cancelled=lambda: False,
        )

    assert seen_range == "bytes=6-"
    assert target.read_bytes() == b"first-second"
    assert progress[-1] == (12, 12)
    assert updated.startswith("2026-08-25")


async def test_cancelled_extract_keeps_resumable_partial_file(tmp_path: Path) -> None:
    class TwoChunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"a" * (1024 * 1024)
            yield b"b" * (1024 * 1024)

    target = tmp_path / "region.osm.pbf"
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, stream=TwoChunks()))
    ) as client:
        with pytest.raises(MapPackDownloadCancelled):
            await _download_extract(
                "https://download.geofabrik.de/test.osm.pbf",
                target,
                client,
                progress=lambda _done, _total, _message: None,
                cancelled=cancelled,
            )

    assert target.with_suffix(".pbf.part").is_file()
    assert not target.exists()
