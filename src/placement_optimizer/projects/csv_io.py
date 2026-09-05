"""Forgiving CSV import and straightforward result export."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import StrEnum

from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.optimization import OptimizationResult
from placement_optimizer.travel import MatrixEntry


class IssueLevel(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ImportIssue:
    row: int
    message: str
    level: IssueLevel = IssueLevel.ERROR
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ImportDraftRow:
    """Original editable values retained even when domain validation fails."""

    row: int
    values: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class ImportBatch[T]:
    items: tuple[T, ...]
    issues: tuple[ImportIssue, ...]
    draft_rows: tuple[ImportDraftRow, ...] = ()

    @property
    def error_count(self) -> int:
        return sum(issue.level is IssueLevel.ERROR for issue in self.issues)


def parse_students_csv(text: str) -> ImportBatch[Student]:
    rows, header_issue = _read_rows(text)
    if header_issue:
        return ImportBatch((), (header_issue,))
    if issue := _missing_known_columns(
        rows,
        {"student_id", "id", "student_name", "name", "address", "latitude", "lat"},
        "No student columns were recognized",
    ):
        return ImportBatch((), (issue,))
    students: list[Student] = []
    issues = _unknown_column_issues(rows, "student")
    seen: set[str] = set()
    for row_number, row in rows:
        student_id = _value(row, "student_id", "id") or _generated_id(rows, seen, "student", "S")
        name = _value(row, "student_name", "name") or student_id
        if student_id in seen:
            issues.append(
                ImportIssue(row_number, f"Duplicate student ID: {student_id}", field="id")
            )
            continue
        try:
            coordinate = _coordinate(row)
        except ValueError as error:
            issues.append(ImportIssue(row_number, str(error), field="coordinates"))
            continue
        seen.add(student_id)
        students.append(
            Student(
                id=student_id,
                name=name,
                address=_value(row, "address") or None,
                coordinate=coordinate,
            )
        )
    return ImportBatch(tuple(students), tuple(issues), _draft_rows(rows))


def parse_locations_csv(text: str) -> ImportBatch[Location]:
    rows, header_issue = _read_rows(text)
    if header_issue:
        return ImportBatch((), (header_issue,))
    if issue := _missing_known_columns(
        rows,
        {"location_id", "id", "location_name", "name", "address", "capacity"},
        "No location columns were recognized",
    ):
        return ImportBatch((), (issue,))
    locations: list[Location] = []
    issues = _unknown_column_issues(rows, "location")
    seen: set[str] = set()
    for row_number, row in rows:
        location_id = _value(row, "location_id", "id") or _generated_id(rows, seen, "location", "L")
        name = _value(row, "location_name", "name") or location_id
        if location_id in seen:
            issues.append(
                ImportIssue(row_number, f"Duplicate location ID: {location_id}", field="id")
            )
            continue
        try:
            coordinate = _coordinate(row)
            capacity_text = _value(row, "capacity")
            if not capacity_text:
                raise ValueError("Capacity is required")
            capacity = int(capacity_text)
            minimum_text = _value(row, "minimum_capacity", "min_capacity", "minimum")
            minimum_capacity = 0 if not minimum_text else int(minimum_text)
            if capacity < 0 or minimum_capacity < 0:
                raise ValueError("Capacity values cannot be negative")
            if minimum_capacity > capacity:
                raise ValueError("Minimum capacity cannot exceed capacity")
        except ValueError as error:
            issues.append(ImportIssue(row_number, str(error), field="capacity"))
            continue
        seen.add(location_id)
        locations.append(
            Location(
                id=location_id,
                name=name,
                capacity=capacity,
                address=_value(row, "address") or None,
                coordinate=coordinate,
                minimum_capacity=minimum_capacity,
            )
        )
    return ImportBatch(tuple(locations), tuple(issues), _draft_rows(rows))


def parse_matrix_csv(text: str) -> ImportBatch[MatrixEntry]:
    rows, header_issue = _read_rows(text)
    if header_issue:
        return ImportBatch((), (header_issue,))
    if issue := _missing_known_columns(
        rows,
        {"student_id", "student"},
        "A student ID column is required",
    ):
        return ImportBatch((), (issue,))
    if issue := _missing_known_columns(
        rows,
        {"location_id", "location"},
        "A location ID column is required",
    ):
        return ImportBatch((), (issue,))
    entries: list[MatrixEntry] = []
    issues: list[ImportIssue] = []
    seen: set[tuple[str, str]] = set()
    for row_number, row in rows:
        student_id = _value(row, "student_id", "student")
        location_id = _value(row, "location_id", "location")
        if not student_id or not location_id:
            issues.append(ImportIssue(row_number, "Student ID and location ID are required"))
            continue
        key = (student_id, location_id)
        if key in seen:
            issues.append(
                ImportIssue(row_number, f"Duplicate matrix pair: {student_id}, {location_id}")
            )
            continue
        try:
            duration = _travel_value(
                row,
                base_names=("duration_seconds",),
                scaled_names=("driving_minutes", "duration_minutes", "minutes"),
                scale=60,
                required=True,
            )
            distance = _travel_value(
                row,
                base_names=("distance_meters",),
                scaled_names=("distance_km", "kilometres", "kilometers"),
                scale=1000,
                required=False,
            )
        except ValueError as error:
            issues.append(ImportIssue(row_number, str(error), field="travel"))
            continue
        seen.add(key)
        entries.append(MatrixEntry(student_id, location_id, distance, duration))
    return ImportBatch(tuple(entries), tuple(issues), _draft_rows(rows))


def export_result_csv(
    result: OptimizationResult,
    students: tuple[Student, ...],
    locations: tuple[Location, ...],
) -> str:
    student_names = {student.id: student.name for student in students}
    location_names = {location.id: location.name for location in locations}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "student_id",
            "student_name",
            "location_id",
            "location_name",
            "driving_minutes",
            "distance_km",
            "preference_rank",
            "changed_from_prior",
        ]
    )
    for placement in result.placements:
        writer.writerow(
            [
                placement.student_id,
                student_names.get(placement.student_id, placement.student_id),
                placement.location_id or "",
                location_names.get(placement.location_id or "", ""),
                (
                    f"{placement.duration_seconds / 60:.1f}"
                    if placement.duration_seconds is not None
                    else ""
                ),
                (
                    f"{placement.distance_meters / 1000:.2f}"
                    if placement.distance_meters is not None
                    else ""
                ),
                placement.preference_rank or "",
                "yes" if placement.changed_from_prior else "no",
            ]
        )
    return output.getvalue()


def _read_rows(text: str) -> tuple[list[tuple[int, dict[str, str]]], ImportIssue | None]:
    cleaned = text.lstrip("\ufeff").strip()
    if not cleaned:
        return [], ImportIssue(1, "The file is empty")
    try:
        dialect = csv.Sniffer().sniff(cleaned[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(cleaned), dialect=dialect)
    if not reader.fieldnames:
        return [], ImportIssue(1, "A header row is required")
    normalized_fields = [_normalize_header(field or "") for field in reader.fieldnames]
    if any(not field for field in normalized_fields):
        return [], ImportIssue(1, "Every column needs a header")
    result: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(reader, start=2):
        normalized = {
            _normalize_header(key or ""): (value or "").strip()
            for key, value in raw.items()
            if key is not None
        }
        if any(normalized.values()):
            result.append((row_number, normalized))
    return result, None


def _draft_rows(
    rows: list[tuple[int, dict[str, str]]],
) -> tuple[ImportDraftRow, ...]:
    return tuple(ImportDraftRow(row_number, tuple(row.items())) for row_number, row in rows)


def _missing_known_columns(
    rows: list[tuple[int, dict[str, str]]],
    known_columns: set[str],
    message: str,
) -> ImportIssue | None:
    if rows and not known_columns.intersection(rows[0][1]):
        return ImportIssue(1, message)
    return None


def _normalize_header(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", " ").split())


def _value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    return ""


def _generated_id(
    rows: list[tuple[int, dict[str, str]]], seen: set[str], kind: str, prefix: str
) -> str:
    reserved = seen | {_value(row, f"{kind}_id", "id") for _, row in rows}
    number = 1
    while f"{prefix}{number:03d}" in reserved:
        number += 1
    return f"{prefix}{number:03d}"


def _unknown_column_issues(rows: list[tuple[int, dict[str, str]]], kind: str) -> list[ImportIssue]:
    known = {
        "id",
        "name",
        f"{kind}_id",
        f"{kind}_name",
        "address",
        "coordinates",
        "latitude",
        "lat",
        "longitude",
        "lon",
        "lng",
    }
    if kind == "location":
        known.update({"capacity", "minimum", "minimum_capacity", "min_capacity"})
    return [
        ImportIssue(
            number,
            f"Column '{field}' is not imported; retained value: {value}",
            IssueLevel.WARNING,
            field,
        )
        for number, row in rows
        for field, value in row.items()
        if field not in known and value
    ]


def _coordinate(row: dict[str, str]) -> Coordinate | None:
    combined = _value(row, "coordinates")
    if combined:
        parts = combined.split(",")
        if len(parts) != 2:
            raise ValueError("Coordinates must be latitude, longitude")
        try:
            coordinate = Coordinate(float(parts[0]), float(parts[1]))
        except ValueError as error:
            raise ValueError("Latitude or longitude is not a valid coordinate") from error
        separate = _coordinate({key: value for key, value in row.items() if key != "coordinates"})
        if separate is not None and separate != coordinate:
            raise ValueError("Combined and separate coordinates disagree; choose one")
        return coordinate
    latitude = _value(row, "latitude", "lat")
    longitude = _value(row, "longitude", "lon", "lng")
    if not latitude and not longitude:
        return None
    if not latitude or not longitude:
        raise ValueError("Latitude and longitude must be supplied together")
    try:
        return Coordinate(float(latitude), float(longitude))
    except ValueError as error:
        raise ValueError("Latitude or longitude is not a valid coordinate") from error


def _travel_value(
    row: dict[str, str],
    *,
    base_names: tuple[str, ...],
    scaled_names: tuple[str, ...],
    scale: int,
    required: bool,
) -> int | None:
    base = _value(row, *base_names)
    scaled = _value(row, *scaled_names)
    raw = base or scaled
    if raw.casefold() in {"no route", "unavailable", "none", "x", "-"}:
        return None
    if not raw:
        if required:
            raise ValueError("Driving time is required; use 'no route' when appropriate")
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"Travel value is not numeric: {raw}") from error
    scaled_value = value if base else value * scale
    if not 0 <= scaled_value <= 1_000_000_000:
        raise ValueError("Travel value is outside the supported range")
    return round(scaled_value)
