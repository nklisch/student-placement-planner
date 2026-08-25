"""Core domain types.

The optimization package intentionally has no web-framework or routing-provider
imports.  This keeps the exact solver usable from scripts, tests, and future
desktop front ends without coupling it to this application's UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


@dataclass(frozen=True, slots=True)
class Coordinate:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a finite number between -90 and 90")
        if not isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a finite number between -180 and 180")


@dataclass(frozen=True, slots=True)
class Student:
    id: str
    name: str
    address: str | None = None
    coordinate: Coordinate | None = None


@dataclass(frozen=True, slots=True)
class Location:
    id: str
    name: str
    capacity: int
    address: str | None = None
    coordinate: Coordinate | None = None
    minimum_capacity: int = 0


class Objective(StrEnum):
    """Supported assignment goals.

    FAIR_DISTANCE is lexicographic: first minimize the longest individual
    journey, then minimize total distance without worsening that longest trip.
    """

    FAIR_DISTANCE = "fair_distance"
    TOTAL_DISTANCE = "total_distance"


@dataclass(frozen=True, slots=True)
class AssignmentProblem:
    students: tuple[Student, ...]
    locations: tuple[Location, ...]
    # Rows are students, columns are locations. None means no road route exists.
    distances_meters: tuple[tuple[int | None, ...], ...]
    durations_seconds: tuple[tuple[int | None, ...], ...] | None = None


@dataclass(frozen=True, slots=True)
class Assignment:
    student_id: str
    location_id: str
    distance_meters: int
    duration_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class LocationUtilization:
    location_id: str
    assigned: int
    capacity: int


@dataclass(frozen=True, slots=True)
class AssignmentResult:
    objective: Objective
    assignments: tuple[Assignment, ...]
    total_distance_meters: int
    maximum_distance_meters: int
    average_distance_meters: float
    location_utilization: tuple[LocationUtilization, ...]
