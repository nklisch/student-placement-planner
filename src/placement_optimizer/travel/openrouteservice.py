"""openrouteservice geocoding and road-matrix providers."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel.base import GeocodingResult, TravelDataError, TravelMatrix

_DEFAULT_BASE_URL = "https://api.openrouteservice.org"


class OpenRouteServiceGeocoder:
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        *,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def geocode(self, address: str) -> GeocodingResult:
        response = await _request(
            self._client,
            "GET",
            f"{self._base_url}/geocode/search",
            self._api_key,
            params={"text": address, "size": 1},
        )
        try:
            feature = response.json()["features"][0]
            longitude, latitude = feature["geometry"]["coordinates"]
            coordinate = Coordinate(latitude=float(latitude), longitude=float(longitude))
            properties = feature.get("properties", {})
            display_name = properties.get("label") or address
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise TravelDataError(f"address was not found: {address}") from error
        return GeocodingResult(coordinate, str(display_name))


class OpenRouteServiceMatrix:
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        block_size: int = 20,
    ) -> None:
        if block_size < 1:
            raise ValueError("block size must be positive")
        self._api_key = api_key
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._block_size = block_size

    async def route_matrix(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> TravelMatrix:
        if not origins:
            return TravelMatrix((), (), source="openrouteservice")
        if not destinations:
            raise TravelDataError("at least one route destination is required")

        distances: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        durations: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        for origin_start in range(0, len(origins), self._block_size):
            origin_block = origins[origin_start : origin_start + self._block_size]
            for destination_start in range(0, len(destinations), self._block_size):
                destination_block = destinations[
                    destination_start : destination_start + self._block_size
                ]
                block_distances, block_durations = await self._route_block(
                    origin_block, destination_block
                )
                for offset, row in enumerate(block_distances):
                    distances[origin_start + offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
                for offset, row in enumerate(block_durations):
                    durations[origin_start + offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
        return TravelMatrix(
            tuple(tuple(row) for row in distances),
            tuple(tuple(row) for row in durations),
            source="openrouteservice",
        )

    async def _route_block(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> tuple[list[list[int | None]], list[list[int | None]]]:
        points = [*origins, *destinations]
        response = await _request(
            self._client,
            "POST",
            f"{self._base_url}/v2/matrix/driving-car",
            self._api_key,
            json={
                "locations": [[point.longitude, point.latitude] for point in points],
                "sources": list(range(len(origins))),
                "destinations": list(range(len(origins), len(points))),
                "metrics": ["distance", "duration"],
                "units": "m",
            },
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise TravelDataError("openrouteservice returned an invalid response") from error
        if not isinstance(payload, dict):
            raise TravelDataError("openrouteservice returned an invalid response")
        return (
            _parse_matrix(payload.get("distances"), len(origins), len(destinations)),
            _parse_matrix(payload.get("durations"), len(origins), len(destinations)),
        )


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    api_key: str,
    **kwargs,
) -> httpx.Response:
    try:
        response = await client.request(
            method,
            url,
            headers={"Authorization": api_key},
            **kwargs,
        )
    except httpx.HTTPError as error:
        raise TravelDataError("openrouteservice could not be reached") from error
    if response.status_code in (401, 403):
        raise TravelDataError("check the openrouteservice API key")
    if response.status_code == 429:
        raise TravelDataError("the openrouteservice free-plan limit was reached")
    if response.status_code >= 400:
        raise TravelDataError(f"openrouteservice returned HTTP {response.status_code}")
    return response


def _parse_matrix(value: object, rows: int, columns: int) -> list[list[int | None]]:
    if not isinstance(value, list) or len(value) != rows:
        raise TravelDataError("openrouteservice returned an incorrectly sized matrix")
    parsed: list[list[int | None]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            raise TravelDataError("openrouteservice returned an incorrectly sized matrix")
        converted: list[int | None] = []
        for item in row:
            if item is None:
                converted.append(None)
            elif isinstance(item, (int, float)) and item >= 0:
                converted.append(round(item))
            else:
                raise TravelDataError("openrouteservice returned an invalid matrix value")
        parsed.append(converted)
    return parsed
