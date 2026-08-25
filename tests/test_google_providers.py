from __future__ import annotations

import httpx
import pytest

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import GoogleGeocoder, GoogleRoutesMatrix, TravelDataError


async def test_google_geocoder_resolves_address() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["address"] == "10 Example Street"
        assert request.url.params["key"] == "secret"
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "formatted_address": "10 Example Street, Exampletown",
                        "geometry": {"location": {"lat": 51.5, "lng": -0.12}},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await GoogleGeocoder("secret", client).geocode("10 Example Street")

    assert result.coordinate == Coordinate(51.5, -0.12)


async def test_google_routes_parses_unordered_elements_and_missing_routes() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        payload = __import__("json").loads(request.content)
        assert len(payload["origins"]) == 2
        assert len(payload["destinations"]) == 2
        return httpx.Response(
            200,
            json=[
                {
                    "originIndex": 1,
                    "destinationIndex": 0,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 3000,
                    "duration": "301.4s",
                    "status": {},
                },
                {
                    "originIndex": 0,
                    "destinationIndex": 1,
                    "condition": "ROUTE_NOT_FOUND",
                    "status": {},
                },
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 1000,
                    "duration": "101s",
                    "status": {},
                },
                {
                    "originIndex": 1,
                    "destinationIndex": 1,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 4000,
                    "duration": "401s",
                    "status": {},
                },
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        matrix = await GoogleRoutesMatrix("secret", client).route_matrix(
            (Coordinate(51.0, -1.0), Coordinate(52.0, -2.0)),
            (Coordinate(53.0, -3.0), Coordinate(54.0, -4.0)),
        )

    assert matrix.distances_meters == ((1000, None), (3000, 4000))
    assert matrix.durations_seconds == ((101, None), (301, 401))


@pytest.mark.parametrize("provider_kind", ["geocoder", "routes"])
async def test_google_transport_errors_do_not_retain_api_keys(provider_kind: str) -> None:
    api_key = "secret-key-that-must-not-survive"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(TravelDataError) as caught:
            if provider_kind == "geocoder":
                await GoogleGeocoder(api_key, client).geocode("10 Example Street")
            else:
                await GoogleRoutesMatrix(api_key, client).route_matrix(
                    (Coordinate(51, -1),),
                    (Coordinate(52, -2),),
                )

    error: BaseException | None = caught.value
    while error is not None:
        assert api_key not in repr(error)
        error = error.__cause__ or error.__context__


async def test_google_routes_rejects_non_finite_distance() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": "Infinity",
                    "duration": "10s",
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TravelDataError, match="invalid matrix element"):
            await GoogleRoutesMatrix("secret", client).route_matrix(
                (Coordinate(51, -1),),
                (Coordinate(52, -2),),
            )
