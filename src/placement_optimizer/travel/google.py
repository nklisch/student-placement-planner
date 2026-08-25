"""Opt-in Google Maps geocoding and Routes API providers.

These providers are never selected implicitly: using them transmits addresses
(to geocoding) and coordinates (to routing) to Google. API keys remain on the
local backend and are not included in errors or responses.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from contextlib import suppress
from itertools import islice

import httpx

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel.base import GeocodingResult, TravelDataError, TravelMatrix

_DURATION_PATTERN = re.compile(r"^(?P<seconds>\d+(?:\.\d+)?)s$")


class GoogleGeocoder:
    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        if not api_key:
            raise ValueError("a Google Maps API key is required")
        self._api_key = api_key
        self._client = client

    async def geocode(self, address: str) -> GeocodingResult:
        response: httpx.Response | None = None
        # Raise after the suppress block: httpx transport errors retain a keyed Request.
        with suppress(httpx.HTTPError):
            response = await self._client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": self._api_key},
            )
        if response is None:
            raise TravelDataError("Google Maps geocoding could not be reached")
        if response.status_code != 200:
            raise TravelDataError(_google_http_message("Google Maps geocoding", response))
        try:
            payload = response.json()
            if payload.get("status") != "OK":
                status = payload.get("status", "UNKNOWN")
                if status == "ZERO_RESULTS":
                    raise TravelDataError(f"address was not found: {address}")
                if status in {"OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"}:
                    raise TravelDataError(
                        "Google Maps geocoding quota was reached; wait and try again"
                    )
                if status in {"REQUEST_DENIED", "INVALID_REQUEST"}:
                    raise TravelDataError(
                        "Google Maps geocoding rejected the request; check the API key, "
                        "enabled APIs, and billing"
                    )
                raise TravelDataError(f"Google Maps geocoding failed with status {status}")
            first = payload["results"][0]
            location = first["geometry"]["location"]
            coordinate = Coordinate(
                latitude=float(location["lat"]),
                longitude=float(location["lng"]),
            )
        except TravelDataError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise TravelDataError("Google Maps geocoding returned invalid data") from error
        return GeocodingResult(
            coordinate=coordinate,
            display_name=str(first.get("formatted_address", address)),
        )


class GoogleRoutesMatrix:
    """Road route matrix using the current Google Routes API."""

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        *,
        block_size: int = 25,
    ) -> None:
        # 25 x 25 reaches the documented non-transit limit of 625 elements.
        if not 1 <= block_size <= 25:
            raise ValueError("Google Routes block_size must be between 1 and 25")
        if not api_key:
            raise ValueError("a Google Maps API key is required")
        self._api_key = api_key
        self._client = client
        self._block_size = block_size

    async def route_matrix(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> TravelMatrix:
        if not origins:
            return TravelMatrix((), (), source="google_routes")
        if not destinations:
            raise TravelDataError("at least one route destination is required")

        distances: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        durations: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        for origin_start, origin_block in _blocks(origins, self._block_size):
            for destination_start, destination_block in _blocks(destinations, self._block_size):
                block_distances, block_durations = await self._route_block(
                    origin_block, destination_block
                )
                for origin_offset, row in enumerate(block_distances):
                    distances[origin_start + origin_offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
                for origin_offset, row in enumerate(block_durations):
                    durations[origin_start + origin_offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row

        return TravelMatrix(
            distances_meters=tuple(tuple(row) for row in distances),
            durations_seconds=tuple(tuple(row) for row in durations),
            source="google_routes",
        )

    async def _route_block(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> tuple[list[list[int | None]], list[list[int | None]]]:
        body = {
            "origins": [_waypoint(point) for point in origins],
            "destinations": [_waypoint(point) for point in destinations],
            "travelMode": "DRIVE",
            # Traffic-unaware gives stable planning distances and allows 625 elements.
            "routingPreference": "TRAFFIC_UNAWARE",
        }
        response: httpx.Response | None = None
        # Raise after the suppress block: httpx transport errors retain a keyed Request.
        with suppress(httpx.HTTPError):
            response = await self._client.post(
                "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
                json=body,
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": (
                        "originIndex,destinationIndex,distanceMeters,duration,status,condition"
                    ),
                },
            )
        if response is None:
            raise TravelDataError("Google Routes could not be reached")
        if response.status_code in {429, 500, 502, 503, 504}:
            response = await self._retry_route_request(body, response)
        if response.status_code != 200:
            raise TravelDataError(_google_http_message("Google Routes", response))
        try:
            elements = response.json()
        except ValueError as error:
            raise TravelDataError("Google Routes returned invalid JSON") from error
        if not isinstance(elements, list):
            raise TravelDataError("Google Routes returned an invalid matrix")

        distances: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        durations: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        for element in elements:
            try:
                origin_index = int(element["originIndex"])
                destination_index = int(element["destinationIndex"])
                if not (0 <= origin_index < len(origins)) or not (
                    0 <= destination_index < len(destinations)
                ):
                    raise ValueError
                if element.get("condition") != "ROUTE_EXISTS":
                    continue
                distances[origin_index][destination_index] = _nonnegative_finite_int(
                    element["distanceMeters"], "distance"
                )
                durations[origin_index][destination_index] = _parse_duration(
                    element.get("duration")
                )
            except (KeyError, TypeError, ValueError) as error:
                raise TravelDataError("Google Routes returned an invalid matrix element") from error
        return distances, durations

    async def _retry_route_request(
        self,
        body: dict[str, object],
        response: httpx.Response,
    ) -> httpx.Response:
        for attempt in range(2):
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(max(float(retry_after), 0.0), 60.0)
            except ValueError:
                delay = float(2**attempt)
            await asyncio.sleep(delay)
            next_response: httpx.Response | None = None
            with suppress(httpx.HTTPError):
                next_response = await self._client.post(
                    "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
                    json=body,
                    headers={
                        "X-Goog-Api-Key": self._api_key,
                        "X-Goog-FieldMask": (
                            "originIndex,destinationIndex,distanceMeters,duration,status,condition"
                        ),
                    },
                )
            if next_response is None:
                raise TravelDataError("Google Routes could not be reached")
            response = next_response
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
        return response


def _google_http_message(service: str, response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return f"{service} rejected the request; check the API key, enabled APIs, and billing"
    if response.status_code == 429:
        return f"{service} quota was reached; wait and try again"
    if 500 <= response.status_code < 600:
        return f"{service} is temporarily unavailable; try again"
    return f"{service} returned HTTP {response.status_code}"


def _waypoint(coordinate: Coordinate) -> dict[str, object]:
    return {
        "waypoint": {
            "location": {
                "latLng": {
                    "latitude": coordinate.latitude,
                    "longitude": coordinate.longitude,
                }
            }
        }
    }


def _parse_duration(value: object) -> int | None:
    if value is None:
        return None
    match = _DURATION_PATTERN.match(str(value))
    if not match:
        raise ValueError("invalid protobuf duration")
    return _nonnegative_finite_int(match.group("seconds"), "duration")


def _nonnegative_finite_int(value: object, label: str) -> int:
    number = float(value)
    if not 0 <= number <= 1_000_000_000:
        raise ValueError(f"invalid {label}")
    return round(number)


def _blocks[T](values: Sequence[T], size: int) -> list[tuple[int, list[T]]]:
    iterator = iter(values)
    result: list[tuple[int, list[T]]] = []
    start = 0
    while block := list(islice(iterator, size)):
        result.append((start, block))
        start += len(block)
    return result
