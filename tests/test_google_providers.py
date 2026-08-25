from __future__ import annotations

import httpx
import pytest

from placement_optimizer.application import TravelInput, TravelWorkflow
from placement_optimizer.domain import Coordinate, Location, Student
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


async def test_google_workflow_sends_addresses_and_coordinates_but_not_names_or_ids() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "geocode" in request.url.path:
            address = request.url.params["address"]
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": f"Matched {address}",
                            "geometry": {"location": {"lat": 51.5, "lng": -0.12}},
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 1200,
                    "duration": "180s",
                    "status": {},
                }
            ],
        )

    transport = httpx.MockTransport(handle)
    workflow = TravelWorkflow(lambda: httpx.AsyncClient(transport=transport, follow_redirects=True))
    travel_input = TravelInput(
        (Student("secret-student-id", "Alice Private", "1 Home Road"),),
        (Location("secret-location-id", "Clinic Private", 1, "2 Work Road"),),
        1,
    )

    review = await workflow.review_google(travel_input, "secret-key")
    matrix = await workflow.calculate_google(review, "secret-key")

    assert matrix.distances_meters == ((1200,),)
    wire_text = "\n".join(
        f"{request.url}\n{request.content.decode(errors='ignore')}" for request in requests
    )
    assert "Alice Private" not in wire_text
    assert "Clinic Private" not in wire_text
    assert "secret-student-id" not in wire_text
    assert "secret-location-id" not in wire_text
    assert "1+Home+Road" in wire_text or "1%20Home%20Road" in wire_text


async def test_google_routes_retries_quota_response_then_recovers() -> None:
    calls = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json=[
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_EXISTS",
                    "distanceMeters": 1000,
                    "duration": "100s",
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        matrix = await GoogleRoutesMatrix("secret", client).route_matrix(
            (Coordinate(51, -1),),
            (Coordinate(52, -2),),
        )

    assert calls == 2
    assert matrix.durations_seconds == ((100,),)


async def test_google_routes_permission_error_is_actionable_and_key_safe() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "denied"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TravelDataError, match="enabled APIs, and billing") as caught:
            await GoogleRoutesMatrix("secret", client).route_matrix(
                (Coordinate(51, -1),),
                (Coordinate(52, -2),),
            )

    assert "secret" not in repr(caught.value)


@pytest.mark.parametrize(
    "elements, message",
    [
        ([], "incomplete matrix"),
        (
            [
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_NOT_FOUND",
                },
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "condition": "ROUTE_NOT_FOUND",
                },
            ],
            "invalid matrix element",
        ),
    ],
)
async def test_google_routes_rejects_missing_or_duplicate_elements(elements, message) -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=elements)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TravelDataError, match=message):
            await GoogleRoutesMatrix("secret", client).route_matrix(
                (Coordinate(51, -1),),
                (Coordinate(52, -2),),
            )


async def test_google_routes_accepts_omitted_zero_fields() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "status": {},
                    "condition": "ROUTE_EXISTS",
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        matrix = await GoogleRoutesMatrix("secret", client).route_matrix(
            (Coordinate(51, -1),),
            (Coordinate(51, -1),),
        )

    assert matrix.distances_meters == ((0,),)
    assert matrix.durations_seconds == ((0,),)


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
