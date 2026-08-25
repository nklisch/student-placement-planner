from __future__ import annotations

from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.travel import (
    GeocodingResult,
    MatrixEntry,
    TravelMatrix,
    build_travel_matrix,
    matrix_from_entries,
)


class RecordingGeocoder:
    def __init__(self) -> None:
        self.addresses: list[str] = []

    async def geocode(self, address: str) -> GeocodingResult:
        self.addresses.append(address)
        return GeocodingResult(Coordinate(51.0, -1.0), f"Resolved {address}")


class RecordingRouter:
    def __init__(self) -> None:
        self.calls = 0

    async def route_matrix(self, origins, destinations) -> TravelMatrix:
        self.calls += 1
        return TravelMatrix(
            distances_meters=tuple(tuple(1000 for _ in destinations) for _ in origins),
            durations_seconds=tuple(tuple(120 for _ in destinations) for _ in origins),
            source="test",
        )


async def test_build_matrix_geocodes_repeated_address_once() -> None:
    students = (
        Student("s1", "One", "1 Shared Road"),
        Student("s2", "Two", "  1 shared   road "),
    )
    locations = (Location("l1", "Placement", 2, "5 School Road"),)
    geocoder = RecordingGeocoder()
    router = RecordingRouter()

    matrix = await build_travel_matrix(students, locations, geocoder, router)

    assert geocoder.addresses == ["1 Shared Road", "5 School Road"]
    assert router.calls == 1
    assert matrix.distances_meters == ((1000,), (1000,))


def test_manual_matrix_is_ordered_by_student_and_location_ids() -> None:
    students = (Student("s1", "One"), Student("s2", "Two"))
    locations = (Location("l1", "One", 1), Location("l2", "Two", 1))
    entries = (
        MatrixEntry("s2", "l2", 4000, 500),
        MatrixEntry("s1", "l2", 2000, 300),
        MatrixEntry("s2", "l1", 3000, 400),
        MatrixEntry("s1", "l1", 1000, 200),
    )

    matrix = matrix_from_entries(students, locations, entries)

    assert matrix.distances_meters == ((1000, 2000), (3000, 4000))
    assert matrix.durations_seconds == ((200, 300), (400, 500))
    assert matrix.source == "offline_matrix"
