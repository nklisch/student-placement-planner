"""Providers for self-hosted Nominatim geocoding and OSRM road routing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from itertools import islice
from urllib.parse import quote

import httpx

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel.base import GeocodingResult, TravelDataError, TravelMatrix


class NominatimGeocoder:
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        *,
        country_codes: str | None = None,
        minimum_interval_seconds: float = 0,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum request interval cannot be negative")
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._country_codes = country_codes
        self._minimum_interval_seconds = minimum_interval_seconds
        self._last_request_started: float | None = None

    async def geocode(self, address: str) -> GeocodingResult:
        if self._last_request_started is not None:
            remaining = self._minimum_interval_seconds - (
                time.monotonic() - self._last_request_started
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request_started = time.monotonic()
        params: dict[str, str | int] = {
            "q": address,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 0,
        }
        if self._country_codes:
            params["countrycodes"] = self._country_codes
        search_url = (
            self._base_url if self._base_url.endswith("/search") else f"{self._base_url}/search"
        )
        try:
            response = await self._client.get(search_url, params=params)
        except httpx.HTTPError as error:
            raise TravelDataError("the configured geocoder could not be reached") from error
        if response.status_code != 200:
            raise TravelDataError(f"the configured geocoder returned HTTP {response.status_code}")
        try:
            results = response.json()
            first = results[0]
            coordinate = Coordinate(latitude=float(first["lat"]), longitude=float(first["lon"]))
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise TravelDataError(f"address was not found: {address}") from error
        return GeocodingResult(
            coordinate=coordinate,
            display_name=str(first.get("display_name", address)),
        )


class OsrmRouteMatrix:
    """Road matrices from an OSRM Table API, split to avoid oversized URLs."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        *,
        profile: str = "driving",
        block_size: int = 40,
    ) -> None:
        if block_size < 1:
            raise ValueError("block_size must be positive")
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._profile = profile
        self._block_size = block_size

    async def route_matrix(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> TravelMatrix:
        if not origins:
            return TravelMatrix((), (), source="local_osrm")
        if not destinations:
            raise TravelDataError("at least one route destination is required")

        distances: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        durations: list[list[int | None]] = [[None] * len(destinations) for _ in origins]

        for origin_start, origin_block in _blocks(origins, self._block_size):
            for destination_start, destination_block in _blocks(destinations, self._block_size):
                block_distances, block_durations = await self._route_block(
                    origin_block, destination_block
                )
                for row_offset, row in enumerate(block_distances):
                    distances[origin_start + row_offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
                for row_offset, row in enumerate(block_durations):
                    durations[origin_start + row_offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row

        return TravelMatrix(
            distances_meters=tuple(tuple(row) for row in distances),
            durations_seconds=tuple(tuple(row) for row in durations),
            source="community_osrm",
        )

    async def _route_block(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> tuple[list[list[int | None]], list[list[int | None]]]:
        points = [*origins, *destinations]
        coordinates = ";".join(f"{point.longitude:.7f},{point.latitude:.7f}" for point in points)
        source_indexes = ";".join(str(index) for index in range(len(origins)))
        destination_indexes = ";".join(str(index) for index in range(len(origins), len(points)))
        url = f"{self._base_url}/table/v1/{quote(self._profile, safe='')}/{coordinates}"
        try:
            response = await self._client.get(
                url,
                params={
                    "sources": source_indexes,
                    "destinations": destination_indexes,
                    "annotations": "distance,duration",
                    "skip_waypoints": "true",
                },
            )
        except httpx.HTTPError as error:
            raise TravelDataError("the configured road router could not be reached") from error
        if response.status_code != 200:
            raise TravelDataError(
                f"the configured road router returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise TravelDataError("the configured road router returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise TravelDataError("the configured road router returned an invalid response")
        if payload.get("code") != "Ok":
            raise TravelDataError(f"road routing failed with code {payload.get('code', 'unknown')}")
        return (
            _parse_osrm_matrix(payload.get("distances"), len(origins), len(destinations)),
            _parse_osrm_matrix(payload.get("durations"), len(origins), len(destinations)),
        )


def _parse_osrm_matrix(
    value: object,
    rows: int,
    columns: int,
) -> list[list[int | None]]:
    if not isinstance(value, list) or len(value) != rows:
        raise TravelDataError("road router returned an incorrectly sized matrix")
    parsed: list[list[int | None]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            raise TravelDataError("road router returned an incorrectly sized matrix")
        try:
            parsed.append(
                [None if cell is None else _nonnegative_finite_cell(cell) for cell in row]
            )
        except (TypeError, ValueError) as error:
            raise TravelDataError("road router returned an invalid matrix value") from error
    return parsed


def _nonnegative_finite_cell(value: object) -> int:
    number = float(value)
    if not 0 <= number <= 1_000_000_000:
        raise ValueError("matrix value is outside the supported range")
    return round(number)


def _blocks[T](values: Sequence[T], size: int) -> list[tuple[int, list[T]]]:
    iterator = iter(values)
    result: list[tuple[int, list[T]]] = []
    start = 0
    while block := list(islice(iterator, size)):
        result.append((start, block))
        start += len(block)
    return result
