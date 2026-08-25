"""Provider-neutral travel data interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from placement_optimizer.domain import Coordinate


class TravelDataError(RuntimeError):
    """Geocoding or road-routing data could not be obtained or validated."""

    def __init__(self, message: str, *, item_ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.item_ids = item_ids


@dataclass(frozen=True, slots=True)
class GeocodingResult:
    coordinate: Coordinate
    display_name: str


@dataclass(frozen=True, slots=True)
class TravelMatrix:
    distances_meters: tuple[tuple[int | None, ...], ...]
    durations_seconds: tuple[tuple[int | None, ...], ...]
    source: str


@dataclass(frozen=True, slots=True)
class MatrixEntry:
    student_id: str
    location_id: str
    distance_meters: int | None
    duration_seconds: int | None = None


class Geocoder(Protocol):
    async def geocode(self, address: str) -> GeocodingResult:
        """Resolve one address or raise TravelDataError."""
        ...


class RouteMatrixProvider(Protocol):
    async def route_matrix(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> TravelMatrix:
        """Calculate origin-to-destination road travel values."""
        ...
