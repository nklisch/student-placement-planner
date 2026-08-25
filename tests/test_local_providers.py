from __future__ import annotations

import httpx
import pytest

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import NominatimGeocoder, OsrmRouteMatrix, TravelDataError


async def test_nominatim_geocoder_sends_only_address_data() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[{"lat": "51.501", "lon": "-0.141", "display_name": "Resolved"}],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await NominatimGeocoder(
            "http://127.0.0.1:8080", client, country_codes="gb"
        ).geocode("10 Example Street")

    assert result.coordinate == Coordinate(51.501, -0.141)
    assert requests[0].url.path == "/search"
    assert requests[0].url.params["q"] == "10 Example Street"
    assert requests[0].url.params["countrycodes"] == "gb"


async def test_osrm_matrix_maps_sources_to_destinations() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/table/v1/driving/")
        assert request.url.params["sources"] == "0;1"
        assert request.url.params["destinations"] == "2"
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "distances": [[1200.4], [2500.6]],
                "durations": [[180.2], [360.8]],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        matrix = await OsrmRouteMatrix("http://127.0.0.1:5000", client).route_matrix(
            (Coordinate(51.0, -1.0), Coordinate(52.0, -2.0)),
            (Coordinate(53.0, -3.0),),
        )

    assert matrix.distances_meters == ((1200,), (2501,))
    assert matrix.durations_seconds == ((180,), (361,))


@pytest.mark.parametrize(
    "payload",
    [[], {"code": "Ok", "distances": [["Infinity"]], "durations": [[10]]}],
)
async def test_osrm_malformed_payload_is_a_recoverable_error(payload: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TravelDataError):
            await OsrmRouteMatrix("http://127.0.0.1:5000", client).route_matrix(
                (Coordinate(51, -1),),
                (Coordinate(52, -2),),
            )
