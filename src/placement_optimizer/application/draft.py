"""Mutable, UI-neutral draft state for spreadsheet-style desktop editing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from placement_optimizer.application.models import PlacementProject, TravelInput
from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    OptimizationConfig,
    Preference,
    StudentLocationPair,
)
from placement_optimizer.travel import TravelMatrix


class DraftArea(StrEnum):
    STUDENTS = "students"
    LOCATIONS = "locations"
    RULES = "rules"
    TRAVEL = "travel"


class TravelMode(StrEnum):
    MANUAL = "manual"
    OFFLINE = "offline"
    COMMUNITY = "community"
    OPENROUTESERVICE = "openrouteservice"
    GOOGLE = "google"


@dataclass(frozen=True, slots=True)
class StudentDraft:
    key: str
    name: str = ""
    id: str = ""
    address: str = ""
    coordinates: str = ""


@dataclass(frozen=True, slots=True)
class LocationDraft:
    key: str
    name: str = ""
    id: str = ""
    capacity: str = ""
    minimum_capacity: str = ""
    address: str = ""
    coordinates: str = ""


@dataclass(frozen=True, slots=True)
class DraftIssue:
    area: DraftArea
    message: str
    row_key: str | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class DraftReadiness:
    ready: bool
    students_ready: bool
    locations_ready: bool
    travel_ready: bool
    missing_travel_cells: int
    issues: tuple[DraftIssue, ...]


@dataclass(frozen=True, slots=True)
class DraftBuildResult:
    project: PlacementProject | None
    readiness: DraftReadiness


@dataclass(frozen=True, slots=True)
class DraftGridSnapshot:
    students: tuple[StudentDraft, ...]
    locations: tuple[LocationDraft, ...]
    rules: AssignmentRules
    manual_times: tuple[tuple[tuple[str, str], str], ...]
    manual_distances_meters: tuple[tuple[tuple[str, str], int], ...]


class DraftSession:
    """Owns raw editable values, versioning, and conversion to a valid project.

    The class has no Qt imports. Table models can mutate it on the UI thread and
    test every state transition without constructing widgets.
    """

    def __init__(self, name: str = "Untitled placement") -> None:
        self.name = name
        self.students: list[StudentDraft] = []
        self.locations: list[LocationDraft] = []
        self.rules = AssignmentRules()
        self.optimization = OptimizationConfig()
        self.travel_mode = TravelMode.MANUAL
        self.manual_times: dict[tuple[str, str], str] = {}
        self.manual_distances_meters: dict[tuple[str, str], int] = {}
        self.calculated_matrix: TravelMatrix | None = None
        self._calculated_travel_version = -1
        self.version = 0
        self.model_version = 0
        self.travel_input_version = 0
        self.saved_version = 0
        self.result_model_version: int | None = None
        self._next_student_key = 1
        self._next_location_key = 1

    @classmethod
    def from_saved_draft(
        cls,
        *,
        name: str,
        students: tuple[StudentDraft, ...],
        locations: tuple[LocationDraft, ...],
        rules: AssignmentRules,
        optimization: OptimizationConfig,
        travel_mode: TravelMode,
        manual_times: dict[tuple[str, str], str],
        manual_distances_meters: dict[tuple[str, str], int],
        calculated_matrix: TravelMatrix | None = None,
        calculated_travel_is_stale: bool = False,
    ) -> DraftSession:
        session = cls(name)
        session.students[:] = students
        session.locations[:] = locations
        session.rules = rules
        session.optimization = optimization
        session.travel_mode = travel_mode
        session.manual_times = dict(manual_times)
        session.manual_distances_meters = dict(manual_distances_meters)
        session.calculated_matrix = calculated_matrix
        session._calculated_travel_version = (
            -1 if calculated_travel_is_stale else session.travel_input_version
        )
        session._next_student_key = _next_key_number(
            "student-row-", (student.key for student in students)
        )
        session._next_location_key = _next_key_number(
            "location-row-", (location.key for location in locations)
        )
        session.saved_version = session.version
        return session

    @classmethod
    def from_project(cls, project: PlacementProject) -> DraftSession:
        session = cls(project.name)
        for student in project.students:
            session.students.append(
                StudentDraft(
                    key=session._student_key(),
                    id=student.id,
                    name=student.name,
                    address=student.address or "",
                    coordinates=_format_coordinate(student.coordinate),
                )
            )
        for location in project.locations:
            session.locations.append(
                LocationDraft(
                    key=session._location_key(),
                    id=location.id,
                    name=location.name,
                    capacity=str(location.capacity),
                    minimum_capacity=(
                        str(location.minimum_capacity) if location.minimum_capacity else ""
                    ),
                    address=location.address or "",
                    coordinates=_format_coordinate(location.coordinate),
                )
            )
        session.rules = project.rules
        session.optimization = project.optimization
        if project.travel_matrix is not None:
            session.calculated_matrix = project.travel_matrix
            session._calculated_travel_version = session.travel_input_version
            session._load_matrix_into_manual_times(project.travel_matrix)
        session.saved_version = session.version
        return session

    @property
    def is_modified(self) -> bool:
        return self.version != self.saved_version

    @property
    def results_are_stale(self) -> bool:
        return (
            self.result_model_version is not None
            and self.result_model_version != self.model_version
        )

    @property
    def calculated_travel_is_stale(self) -> bool:
        if self.calculated_matrix is None:
            return False
        version_changed = self._calculated_travel_version != self.travel_input_version
        source = self.calculated_matrix.source
        expected_source = {
            TravelMode.OFFLINE: lambda value: value.startswith("valhalla:"),
            TravelMode.COMMUNITY: lambda value: value == "community_osrm",
            TravelMode.OPENROUTESERVICE: lambda value: value == "openrouteservice",
            TravelMode.GOOGLE: lambda value: value == "google_routes",
        }.get(self.travel_mode)
        mode_changed = expected_source is not None and not expected_source(source)
        return version_changed or mode_changed

    def set_name(self, name: str) -> None:
        if name != self.name:
            self.name = name
            self._bump(model=False)

    def add_student(self, draft: StudentDraft | None = None) -> StudentDraft:
        item = draft or StudentDraft(
            key=self._student_key(),
            id=self._next_id("S", (student.id for student in self.students)),
        )
        if any(student.key == item.key for student in self.students):
            item = replace(item, key=self._student_key())
        self.students.append(item)
        self._bump(travel=True)
        return item

    def update_student(self, index: int, **changes: str) -> StudentDraft:
        original = self.students[index]
        updated = replace(original, **changes)
        self.students[index] = updated
        if original.id != updated.id:
            self.rules = _rename_student(self.rules, original.id, updated.id)
        self._bump(travel=True)
        return updated

    def remove_students(self, indexes: list[int]) -> None:
        removed = {
            self.students[index].id
            for index in sorted(set(indexes))
            if 0 <= index < len(self.students)
        }
        removed_keys = {
            self.students[index].key
            for index in sorted(set(indexes))
            if 0 <= index < len(self.students)
        }
        self.students[:] = [
            student for index, student in enumerate(self.students) if index not in set(indexes)
        ]
        self.manual_times = {
            key: value for key, value in self.manual_times.items() if key[0] not in removed_keys
        }
        self.manual_distances_meters = {
            key: value
            for key, value in self.manual_distances_meters.items()
            if key[0] not in removed_keys
        }
        self.rules = _without_students(self.rules, removed)
        self._bump(travel=True)

    def add_location(self, draft: LocationDraft | None = None) -> LocationDraft:
        item = draft or LocationDraft(
            key=self._location_key(),
            id=self._next_id("L", (location.id for location in self.locations)),
        )
        if any(location.key == item.key for location in self.locations):
            item = replace(item, key=self._location_key())
        self.locations.append(item)
        self._bump(travel=True)
        return item

    def update_location(self, index: int, **changes: str) -> LocationDraft:
        original = self.locations[index]
        updated = replace(original, **changes)
        self.locations[index] = updated
        if original.id != updated.id:
            self.rules = _rename_location(self.rules, original.id, updated.id)
        self._bump(travel=True)
        return updated

    def remove_locations(self, indexes: list[int]) -> None:
        index_set = set(indexes)
        removed = {
            self.locations[index].id for index in index_set if 0 <= index < len(self.locations)
        }
        removed_keys = {
            self.locations[index].key for index in index_set if 0 <= index < len(self.locations)
        }
        self.locations[:] = [
            location for index, location in enumerate(self.locations) if index not in index_set
        ]
        self.manual_times = {
            key: value for key, value in self.manual_times.items() if key[1] not in removed_keys
        }
        self.manual_distances_meters = {
            key: value
            for key, value in self.manual_distances_meters.items()
            if key[1] not in removed_keys
        }
        self.rules = _without_locations(self.rules, removed)
        self._bump(travel=True)

    def set_rules(self, rules: AssignmentRules) -> None:
        if rules != self.rules:
            self.rules = rules
            self._bump()

    def set_optimization(self, optimization: OptimizationConfig) -> None:
        if optimization != self.optimization:
            self.optimization = optimization
            self._bump()

    def set_travel_mode(self, mode: TravelMode) -> None:
        if mode is not self.travel_mode:
            self.travel_mode = mode
            self._bump()

    def set_manual_time(self, student_key: str, location_key: str, value: str) -> None:
        cell = (student_key, location_key)
        cleaned = value.strip()
        if self.manual_times.get(cell, "") != cleaned:
            if cleaned:
                self.manual_times[cell] = cleaned
            else:
                self.manual_times.pop(cell, None)
            if self.calculated_matrix is not None:
                self._calculated_travel_version = -1
            self._bump()

    def set_manual_distance(
        self,
        student_key: str,
        location_key: str,
        distance_meters: int | None,
    ) -> None:
        cell = (student_key, location_key)
        if distance_meters is not None and distance_meters < 0:
            raise ValueError("distance cannot be negative")
        previous = self.manual_distances_meters.get(cell)
        if previous != distance_meters:
            if distance_meters is None:
                self.manual_distances_meters.pop(cell, None)
            else:
                self.manual_distances_meters[cell] = distance_meters
            if self.calculated_matrix is not None:
                self._calculated_travel_version = -1
            self._bump()

    def grid_snapshot(self) -> DraftGridSnapshot:
        return DraftGridSnapshot(
            students=tuple(self.students),
            locations=tuple(self.locations),
            rules=self.rules,
            manual_times=tuple(self.manual_times.items()),
            manual_distances_meters=tuple(self.manual_distances_meters.items()),
        )

    def restore_grid_snapshot(self, snapshot: DraftGridSnapshot) -> None:
        self.students[:] = snapshot.students
        self.locations[:] = snapshot.locations
        self.rules = snapshot.rules
        self.manual_times = dict(snapshot.manual_times)
        self.manual_distances_meters = dict(snapshot.manual_distances_meters)
        self._bump(travel=True)

    def set_calculated_matrix(self, matrix: TravelMatrix) -> None:
        self.calculated_matrix = matrix
        self._calculated_travel_version = self.travel_input_version
        self._load_matrix_into_manual_times(matrix)
        self._bump()

    def clear_calculated_matrix(self) -> None:
        if self.calculated_matrix is not None:
            self.calculated_matrix = None
            self._calculated_travel_version = -1
            self._bump()

    def mark_saved(self) -> None:
        self.saved_version = self.version

    def mark_result(self, model_version: int | None = None) -> None:
        """Record which immutable input version produced the displayed result."""

        self.result_model_version = self.model_version if model_version is None else model_version

    def readiness(self) -> DraftReadiness:
        return self.build_project().readiness

    def build_travel_input(self) -> TravelInput | None:
        """Return validated roster data for an off-thread provider operation."""

        issues: list[DraftIssue] = []
        students = self._validated_students(issues)
        locations = self._validated_locations(issues)
        if not students or not locations or issues:
            return None
        return TravelInput(students, locations, self.travel_input_version)

    def build_project(self) -> DraftBuildResult:
        issues: list[DraftIssue] = []
        students = self._validated_students(issues)
        locations = self._validated_locations(issues)
        students_ready = bool(students) and not any(
            issue.area is DraftArea.STUDENTS for issue in issues
        )
        locations_ready = bool(locations) and not any(
            issue.area is DraftArea.LOCATIONS for issue in issues
        )

        travel_matrix: TravelMatrix | None = None
        missing_travel_cells = 0
        if self.travel_mode is TravelMode.MANUAL:
            # Validate retained raw cells even while another step needs attention.
            travel_matrix, missing_travel_cells = self._manual_matrix(issues)
        elif students_ready and locations_ready:
            if self.calculated_matrix is None or self.calculated_travel_is_stale:
                issues.append(
                    DraftIssue(
                        DraftArea.TRAVEL,
                        "Driving times need to be calculated for the current students "
                        "and locations.",
                    )
                )
            else:
                travel_matrix = self.calculated_matrix
        else:
            missing_travel_cells = len(self.students) * len(self.locations)

        travel_ready = (
            students_ready
            and locations_ready
            and travel_matrix is not None
            and not any(issue.area is DraftArea.TRAVEL for issue in issues)
        )
        ready = students_ready and locations_ready and travel_ready
        readiness = DraftReadiness(
            ready=ready,
            students_ready=students_ready,
            locations_ready=locations_ready,
            travel_ready=travel_ready,
            missing_travel_cells=missing_travel_cells,
            issues=tuple(issues),
        )
        if not ready:
            return DraftBuildResult(None, readiness)
        return DraftBuildResult(
            PlacementProject(
                name=self.name.strip() or "Untitled placement",
                students=students,
                locations=locations,
                travel_matrix=travel_matrix,
                rules=self.rules,
                optimization=self.optimization,
            ),
            readiness,
        )

    def _validated_students(self, issues: list[DraftIssue]) -> tuple[Student, ...]:
        result: list[Student] = []
        seen: set[str] = set()
        for row in self.students:
            student_id = row.id.strip()
            name = row.name.strip()
            if not student_id:
                issues.append(DraftIssue(DraftArea.STUDENTS, "ID is required", row.key, "id"))
            elif student_id in seen:
                issues.append(
                    DraftIssue(DraftArea.STUDENTS, f"Duplicate ID {student_id}", row.key, "id")
                )
            if not name:
                issues.append(
                    DraftIssue(DraftArea.STUDENTS, "Student name is required", row.key, "name")
                )
            coordinate = _parse_coordinate(row.coordinates, DraftArea.STUDENTS, row.key, issues)
            seen.add(student_id)
            if student_id and name and not _row_has_issue(issues, DraftArea.STUDENTS, row.key):
                result.append(Student(student_id, name, row.address.strip() or None, coordinate))
        return tuple(result)

    def _validated_locations(self, issues: list[DraftIssue]) -> tuple[Location, ...]:
        result: list[Location] = []
        seen: set[str] = set()
        for row in self.locations:
            location_id = row.id.strip()
            name = row.name.strip()
            if not location_id:
                issues.append(DraftIssue(DraftArea.LOCATIONS, "ID is required", row.key, "id"))
            elif location_id in seen:
                issues.append(
                    DraftIssue(
                        DraftArea.LOCATIONS,
                        f"Duplicate ID {location_id}",
                        row.key,
                        "id",
                    )
                )
            if not name:
                issues.append(
                    DraftIssue(DraftArea.LOCATIONS, "Location name is required", row.key, "name")
                )
            capacity = _parse_capacity(row.capacity, "Capacity", row.key, issues)
            minimum = _parse_capacity(
                row.minimum_capacity or "0",
                "Minimum capacity",
                row.key,
                issues,
            )
            if capacity is not None and minimum is not None and minimum > capacity:
                issues.append(
                    DraftIssue(
                        DraftArea.LOCATIONS,
                        "Minimum capacity cannot exceed capacity",
                        row.key,
                        "minimum_capacity",
                    )
                )
            coordinate = _parse_coordinate(row.coordinates, DraftArea.LOCATIONS, row.key, issues)
            seen.add(location_id)
            if (
                location_id
                and name
                and capacity is not None
                and minimum is not None
                and not _row_has_issue(issues, DraftArea.LOCATIONS, row.key)
            ):
                result.append(
                    Location(
                        location_id,
                        name,
                        capacity,
                        row.address.strip() or None,
                        coordinate,
                        minimum,
                    )
                )
        return tuple(result)

    def _manual_matrix(
        self,
        issues: list[DraftIssue],
    ) -> tuple[TravelMatrix | None, int]:
        durations: list[list[int | None]] = []
        missing = 0
        for student in self.students:
            duration_row: list[int | None] = []
            for location in self.locations:
                raw = self.manual_times.get((student.key, location.key), "").strip()
                if not raw:
                    missing += 1
                    duration_row.append(None)
                    continue
                if raw.casefold() in {"x", "-", "no route"}:
                    duration_row.append(None)
                    continue
                try:
                    minutes = float(raw)
                    if not 0 <= minutes <= 999:
                        raise ValueError
                    duration_row.append(round(minutes * 60))
                except ValueError:
                    issues.append(
                        DraftIssue(
                            DraftArea.TRAVEL,
                            "Enter minutes from 0 to 999, or x for no route",
                            f"{student.key}:{location.key}",
                            "minutes",
                        )
                    )
                    duration_row.append(None)
            durations.append(duration_row)
        if missing:
            issues.append(
                DraftIssue(
                    DraftArea.TRAVEL,
                    f"{missing} driving-time cell(s) still need a value",
                )
            )
        if any(issue.area is DraftArea.TRAVEL for issue in issues):
            return None, missing
        distances = tuple(
            tuple(
                self.manual_distances_meters.get((student.key, location.key))
                for location in self.locations
            )
            for student in self.students
        )
        return (
            TravelMatrix(
                distances_meters=distances,
                durations_seconds=tuple(tuple(row) for row in durations),
                source="manual_times",
            ),
            0,
        )

    def _load_matrix_into_manual_times(self, matrix: TravelMatrix) -> None:
        if len(matrix.durations_seconds) != len(self.students):
            return
        for student_index, student in enumerate(self.students):
            row = matrix.durations_seconds[student_index]
            if len(row) != len(self.locations):
                return
            for location_index, location in enumerate(self.locations):
                duration = row[location_index]
                key = (student.key, location.key)
                self.manual_times[key] = "x" if duration is None else f"{duration / 60:g}"
                if student_index < len(matrix.distances_meters) and location_index < len(
                    matrix.distances_meters[student_index]
                ):
                    distance = matrix.distances_meters[student_index][location_index]
                    if distance is None:
                        self.manual_distances_meters.pop(key, None)
                    else:
                        self.manual_distances_meters[key] = distance

    def _bump(self, *, model: bool = True, travel: bool = False) -> None:
        self.version += 1
        if model:
            self.model_version += 1
        if travel:
            self.travel_input_version += 1

    def _student_key(self) -> str:
        value = f"student-row-{self._next_student_key}"
        self._next_student_key += 1
        return value

    def _location_key(self) -> str:
        value = f"location-row-{self._next_location_key}"
        self._next_location_key += 1
        return value

    @staticmethod
    def _next_id(prefix: str, existing: object) -> str:
        used = {str(value).strip() for value in existing}
        number = 1
        while f"{prefix}{number:03d}" in used:
            number += 1
        return f"{prefix}{number:03d}"


def _next_key_number(prefix: str, keys: Iterable[str]) -> int:
    maximum = 0
    for key in keys:
        value = str(key)
        if value.startswith(prefix) and value[len(prefix) :].isdigit():
            maximum = max(maximum, int(value[len(prefix) :]))
    return maximum + 1


def _parse_coordinate(
    raw: str,
    area: DraftArea,
    row_key: str,
    issues: list[DraftIssue],
) -> Coordinate | None:
    value = raw.strip()
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        issues.append(
            DraftIssue(
                area, "Use latitude, longitude—for example 51.5, -0.12", row_key, "coordinates"
            )
        )
        return None
    try:
        return Coordinate(float(parts[0]), float(parts[1]))
    except ValueError:
        issues.append(
            DraftIssue(area, "Coordinates are outside the valid range", row_key, "coordinates")
        )
        return None


def _parse_capacity(
    raw: str,
    label: str,
    row_key: str,
    issues: list[DraftIssue],
) -> int | None:
    if not raw.strip():
        issues.append(DraftIssue(DraftArea.LOCATIONS, f"{label} is required", row_key, "capacity"))
        return None
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        issues.append(
            DraftIssue(
                DraftArea.LOCATIONS,
                f"{label} must be a whole number of zero or more",
                row_key,
                "capacity",
            )
        )
        return None


def _row_has_issue(issues: list[DraftIssue], area: DraftArea, row_key: str) -> bool:
    return any(issue.area is area and issue.row_key == row_key for issue in issues)


def _format_coordinate(coordinate: Coordinate | None) -> str:
    if coordinate is None:
        return ""
    return f"{coordinate.latitude:g}, {coordinate.longitude:g}"


def _rename_student(rules: AssignmentRules, old: str, new: str) -> AssignmentRules:
    return replace(
        rules,
        eligible_locations=_rename_preferences(rules.eligible_locations, old, new),
        preferences=_rename_preferences(rules.preferences, old, new),
        pinned=_rename_pair_students(rules.pinned, old, new),
        prohibited=_rename_pair_students(rules.prohibited, old, new),
        together=_rename_group_students(rules.together, old, new),
        separate=_rename_group_students(rules.separate, old, new),
        student_commute_limits=tuple(
            (new if student_id == old else student_id, limit)
            for student_id, limit in rules.student_commute_limits
        ),
        prior_assignments=_rename_pair_students(rules.prior_assignments, old, new),
    )


def _rename_location(rules: AssignmentRules, old: str, new: str) -> AssignmentRules:
    def preferences(values: tuple[Preference, ...]) -> tuple[Preference, ...]:
        return tuple(
            Preference(
                value.student_id,
                tuple(
                    new if location_id == old else location_id for location_id in value.location_ids
                ),
            )
            for value in values
        )

    def pairs(values: tuple[StudentLocationPair, ...]) -> tuple[StudentLocationPair, ...]:
        return tuple(
            StudentLocationPair(
                value.student_id,
                new if value.location_id == old else value.location_id,
            )
            for value in values
        )

    return replace(
        rules,
        eligible_locations=preferences(rules.eligible_locations),
        preferences=preferences(rules.preferences),
        pinned=pairs(rules.pinned),
        prohibited=pairs(rules.prohibited),
        prior_assignments=pairs(rules.prior_assignments),
    )


def _without_students(rules: AssignmentRules, removed: set[str]) -> AssignmentRules:
    def preferences(values: tuple[Preference, ...]) -> tuple[Preference, ...]:
        return tuple(value for value in values if value.student_id not in removed)

    def pairs(values: tuple[StudentLocationPair, ...]) -> tuple[StudentLocationPair, ...]:
        return tuple(value for value in values if value.student_id not in removed)

    def groups(values: tuple[GroupRule, ...]) -> tuple[GroupRule, ...]:
        updated = [
            GroupRule(
                tuple(student_id for student_id in value.student_ids if student_id not in removed)
            )
            for value in values
        ]
        return tuple(value for value in updated if len(value.student_ids) >= 2)

    return replace(
        rules,
        eligible_locations=preferences(rules.eligible_locations),
        preferences=preferences(rules.preferences),
        pinned=pairs(rules.pinned),
        prohibited=pairs(rules.prohibited),
        together=groups(rules.together),
        separate=groups(rules.separate),
        student_commute_limits=tuple(
            value for value in rules.student_commute_limits if value[0] not in removed
        ),
        prior_assignments=pairs(rules.prior_assignments),
    )


def _without_locations(rules: AssignmentRules, removed: set[str]) -> AssignmentRules:
    def preferences(
        values: tuple[Preference, ...],
        *,
        keep_empty: bool,
    ) -> tuple[Preference, ...]:
        updated = [
            Preference(
                value.student_id,
                tuple(
                    location_id for location_id in value.location_ids if location_id not in removed
                ),
            )
            for value in values
        ]
        return tuple(value for value in updated if keep_empty or value.location_ids)

    def pairs(values: tuple[StudentLocationPair, ...]) -> tuple[StudentLocationPair, ...]:
        return tuple(value for value in values if value.location_id not in removed)

    return replace(
        rules,
        eligible_locations=preferences(rules.eligible_locations, keep_empty=False),
        preferences=preferences(rules.preferences, keep_empty=False),
        pinned=pairs(rules.pinned),
        prohibited=pairs(rules.prohibited),
        prior_assignments=pairs(rules.prior_assignments),
    )


def _rename_preferences(
    values: tuple[Preference, ...], old: str, new: str
) -> tuple[Preference, ...]:
    return tuple(
        Preference(new if value.student_id == old else value.student_id, value.location_ids)
        for value in values
    )


def _rename_pair_students(
    values: tuple[StudentLocationPair, ...], old: str, new: str
) -> tuple[StudentLocationPair, ...]:
    return tuple(
        StudentLocationPair(
            new if value.student_id == old else value.student_id,
            value.location_id,
        )
        for value in values
    )


def _rename_group_students(
    values: tuple[GroupRule, ...], old: str, new: str
) -> tuple[GroupRule, ...]:
    return tuple(
        GroupRule(
            tuple(new if student_id == old else student_id for student_id in value.student_ids)
        )
        for value in values
    )
