"""Travel-data orchestration independent of provider implementations."""

from __future__ import annotations

from collections.abc import Sequence

from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.travel.base import (
    Geocoder,
    MatrixEntry,
    RouteMatrixProvider,
    TravelDataError,
    TravelMatrix,
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

    cache: dict[str, Coordinate] = {}
    student_coordinates = await _resolve_coordinates(students, geocoder, cache)
    location_coordinates = await _resolve_coordinates(locations, geocoder, cache)
    return await router.route_matrix(student_coordinates, location_coordinates)


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


async def _resolve_coordinates(
    places: Sequence[Student] | Sequence[Location],
    geocoder: Geocoder,
    cache: dict[str, Coordinate],
) -> tuple[Coordinate, ...]:
    coordinates: list[Coordinate] = []
    for place in places:
        if place.coordinate is not None:
            coordinates.append(place.coordinate)
            continue
        address = (place.address or "").strip()
        if not address:
            raise TravelDataError(
                "an address or latitude/longitude is required",
                item_ids=(place.id,),
            )
        normalized = " ".join(address.casefold().split())
        if normalized not in cache:
            try:
                cache[normalized] = (await geocoder.geocode(address)).coordinate
            except TravelDataError as error:
                if error.item_ids:
                    raise
                raise TravelDataError(str(error), item_ids=(place.id,)) from error
        coordinates.append(cache[normalized])
    return tuple(coordinates)
