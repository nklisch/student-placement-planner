"""Travel-data orchestration independent of provider implementations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.travel.base import (
    Geocoder,
    GeocodingResult,
    MatrixEntry,
    RouteMatrixProvider,
    TravelDataError,
    TravelMatrix,
)


@dataclass(frozen=True, slots=True)
class ResolvedPlace:
    item_id: str
    name: str
    entered_address: str
    matched_address: str
    coordinate: Coordinate


@dataclass(frozen=True, slots=True)
class TravelCoordinateReview:
    students: tuple[ResolvedPlace, ...]
    locations: tuple[ResolvedPlace, ...]


async def resolve_travel_coordinates(
    students: Sequence[Student],
    locations: Sequence[Location],
    geocoder: Geocoder,
) -> TravelCoordinateReview:
    """Resolve only address data so users can review matches before routing."""

    cache: dict[str, GeocodingResult] = {}
    return TravelCoordinateReview(
        students=await _resolve_places(students, geocoder, cache),
        locations=await _resolve_places(locations, geocoder, cache),
    )


async def route_reviewed_matrix(
    review: TravelCoordinateReview,
    router: RouteMatrixProvider,
) -> TravelMatrix:
    """Calculate a matrix from coordinates the user has already reviewed."""

    return await router.route_matrix(
        tuple(item.coordinate for item in review.students),
        tuple(item.coordinate for item in review.locations),
    )


async def build_travel_matrix(
    students: Sequence[Student],
    locations: Sequence[Location],
    geocoder: Geocoder,
    router: RouteMatrixProvider,
) -> TravelMatrix:
    """Resolve missing coordinates and calculate the road route matrix.

    An in-request cache avoids sending a repeated household or location address
    to a geocoding provider more than once. Nothing is persisted after the call.
    """

    review = await resolve_travel_coordinates(students, locations, geocoder)
    return await route_reviewed_matrix(review, router)


def matrix_from_entries(
    students: Sequence[Student],
    locations: Sequence[Location],
    entries: Sequence[MatrixEntry],
) -> TravelMatrix:
    """Build a fully offline road matrix from explicit student/location cells."""

    student_indexes = {student.id: index for index, student in enumerate(students)}
    location_indexes = {location.id: index for index, location in enumerate(locations)}
    distances: list[list[int | None]] = [[None] * len(locations) for _ in students]
    durations: list[list[int | None]] = [[None] * len(locations) for _ in students]
    seen: set[tuple[int, int]] = set()

    for entry in entries:
        if entry.student_id not in student_indexes:
            raise TravelDataError(f"matrix contains unknown student id: {entry.student_id}")
        if entry.location_id not in location_indexes:
            raise TravelDataError(f"matrix contains unknown location id: {entry.location_id}")
        student_index = student_indexes[entry.student_id]
        location_index = location_indexes[entry.location_id]
        cell = (student_index, location_index)
        if cell in seen:
            raise TravelDataError(
                f"matrix repeats student/location pair: {entry.student_id}, {entry.location_id}"
            )
        if entry.distance_meters is not None and entry.distance_meters < 0:
            raise TravelDataError("matrix distances cannot be negative")
        if entry.duration_seconds is not None and entry.duration_seconds < 0:
            raise TravelDataError("matrix durations cannot be negative")
        seen.add(cell)
        distances[student_index][location_index] = entry.distance_meters
        durations[student_index][location_index] = entry.duration_seconds

    expected_cells = len(students) * len(locations)
    if len(seen) != expected_cells:
        missing = expected_cells - len(seen)
        raise TravelDataError(
            f"matrix is missing {missing} student/location pair(s); "
            "use a blank distance for no route"
        )
    return TravelMatrix(
        distances_meters=tuple(tuple(row) for row in distances),
        durations_seconds=tuple(tuple(row) for row in durations),
        source="offline_matrix",
    )


async def _resolve_places(
    places: Sequence[Student] | Sequence[Location],
    geocoder: Geocoder,
    cache: dict[str, GeocodingResult],
) -> tuple[ResolvedPlace, ...]:
    resolved: list[ResolvedPlace] = []
    for place in places:
        address = (place.address or "").strip()
        if place.coordinate is not None:
            resolved.append(
                ResolvedPlace(
                    place.id,
                    place.name,
                    address,
                    "Coordinates provided",
                    place.coordinate,
                )
            )
            continue
        if not address:
            raise TravelDataError(
                "an address or latitude/longitude is required",
                item_ids=(place.id,),
            )
        normalized = " ".join(address.casefold().split())
        if normalized not in cache:
            try:
                cache[normalized] = await geocoder.geocode(address)
            except TravelDataError as error:
                if error.item_ids:
                    raise
                raise TravelDataError(str(error), item_ids=(place.id,)) from error
        result = cache[normalized]
        resolved.append(
            ResolvedPlace(
                place.id,
                place.name,
                address,
                result.display_name,
                result.coordinate,
            )
        )
    return tuple(resolved)
