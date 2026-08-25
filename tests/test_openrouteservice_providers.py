from __future__ import annotations

import json

import httpx
import pytest

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import (
    OpenRouteServiceGeocoder,
    OpenRouteServiceMatrix,
    TravelDataError,
)

pytestmark = pytest.mark.asyncio


async def test_openrouteservice_geocoder_uses_header_and_only_address_data() -> None:
    seen: httpx.Request | None = None

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen = request
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [8.69, 49.41]},
                        "properties": {"label": "Heidelberg, Germany"},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await OpenRouteServiceGeocoder(
            "secret-key", client, base_url="https://ors.test"
        ).geocode("Heidelberg")

    assert result.coordinate == Coordinate(49.41, 8.69)
    assert seen is not None
    assert seen.headers["Authorization"] == "secret-key"
    assert "secret-key" not in str(seen.url)
    assert seen.url.params["text"] == "Heidelberg"


async def test_openrouteservice_matrix_reassembles_blocks() -> None:
    requests: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        rows = len(payload["sources"])
        columns = len(payload["destinations"])
        return httpx.Response(
            200,
            json={
                "distances": [[1200.4] * columns for _ in range(rows)],
                "durations": [[125.6] * columns for _ in range(rows)],
            },
        )

    origins = tuple(Coordinate(49 + index / 100, 8) for index in range(3))
    destinations = tuple(Coordinate(50, 8 + index / 100) for index in range(3))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        matrix = await OpenRouteServiceMatrix(
            "secret", client, base_url="https://ors.test", block_size=2
        ).route_matrix(origins, destinations)

    assert len(requests) == 4
    assert matrix.source == "openrouteservice"
    assert matrix.distances_meters == ((1200, 1200, 1200),) * 3
    assert matrix.durations_seconds == ((126, 126, 126),) * 3


@pytest.mark.parametrize(
    "status, message",
    [(401, "API key"), (429, "free-plan limit"), (500, "HTTP 500")],
)
async def test_openrouteservice_errors_are_actionable(status: int, message: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status))
    ) as client:
        with pytest.raises(TravelDataError, match=message):
            await OpenRouteServiceGeocoder("secret", client, base_url="https://ors.test").geocode(
                "Somewhere"
            )
