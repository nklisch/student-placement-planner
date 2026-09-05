from __future__ import annotations

import pytest

from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.travel import (
    GeocodingResult,
    MatrixEntry,
    TravelDataError,
    TravelMatrix,
    build_travel_matrix,
    matrix_from_entries,
    resolve_travel_coordinates,
    route_reviewed_matrix,
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


async def test_review_preserves_successes_and_every_unresolved_row() -> None:
    class PartialGeocoder(RecordingGeocoder):
        async def geocode(self, address):
            if address == "Bad address":
                self.addresses.append(address)
                raise TravelDataError("No match; correct the address or enter coordinates")
            return await super().geocode(address)

    geocoder = PartialGeocoder()
    students = (
        Student("s1", "Missing"),
        Student("s2", "Bad", "Bad address"),
        Student("s3", "Good", "Good address"),
    )
    locations = (Location("l1", "Work", 3, coordinate=Coordinate(52, -1)),)
    review = await resolve_travel_coordinates(students, locations, geocoder)

    assert len(review.students) == 3
    assert review.students[0].coordinate is None
    assert "required" in review.students[0].error
    assert review.students[1].coordinate is None
    assert "No match" in review.students[1].error
    assert review.students[2].coordinate == Coordinate(51, -1)
    assert "override" in review.locations[0].source
    assert geocoder.addresses == ["Bad address", "Good address"]
    router = RecordingRouter()
    with pytest.raises(TravelDataError) as error:
        await route_reviewed_matrix(review, router)
    assert error.value.item_ids == ("s1", "s2")
    assert router.calls == 0


async def test_review_cancellation_is_not_an_unresolved_match() -> None:
    import asyncio

    class CancelledGeocoder:
        async def geocode(self, address):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await resolve_travel_coordinates(
            (Student("s1", "One", "An address"),), (), CancelledGeocoder()
        )
