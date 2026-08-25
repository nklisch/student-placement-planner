"""Explicit, versioned local project save and load.

Project saving is user initiated. The atomic replace is a reliability measure:
a power loss should leave either the previous complete file or the new one.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from placement_optimizer.application import (
    DraftSession,
    LocationDraft,
    PlacementProject,
    StudentDraft,
    TravelMode,
)
from placement_optimizer.domain import Coordinate, Location, Student
from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    ObjectiveKind,
    OptimizationConfig,
    Preference,
    StudentLocationPair,
)
from placement_optimizer.travel import TravelMatrix

_SCHEMA_VERSION = 1
_NonNegativeInt = Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
_Latitude = Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
_Longitude = Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
_PositiveSeconds = Annotated[float, Field(strict=True, gt=0, le=3600, allow_inf_nan=False)]


class ProjectFileError(ValueError):
    """A project file is unreadable or incompatible; a blank project can still open."""


class _DocumentModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _CoordinateDocument(_DocumentModel):
    latitude: _Latitude
    longitude: _Longitude


class _StudentDocument(_DocumentModel):
    id: StrictStr
    name: StrictStr
    address: StrictStr | None = None
    coordinate: _CoordinateDocument | None = None


class _LocationDocument(_DocumentModel):
    id: StrictStr
    name: StrictStr
    capacity: _NonNegativeInt
    minimum_capacity: _NonNegativeInt = 0
    address: StrictStr | None = None
    coordinate: _CoordinateDocument | None = None

    @model_validator(mode="after")
    def minimum_fits_capacity(self) -> _LocationDocument:
        if self.minimum_capacity > self.capacity:
            raise ValueError("minimum capacity cannot exceed capacity")
        return self


class _TravelMatrixDocument(_DocumentModel):
    source: StrictStr = "saved_project"
    durations_seconds: list[list[_NonNegativeInt | None]]
    distances_meters: list[list[_NonNegativeInt | None]] | None = None


class _PreferenceDocument(_DocumentModel):
    student_id: StrictStr
    location_ids: list[StrictStr]


class _PairDocument(_DocumentModel):
    student_id: StrictStr
    location_id: StrictStr


class _RulesDocument(_DocumentModel):
    eligible_locations: list[_PreferenceDocument] = Field(default_factory=list)
    preferences: list[_PreferenceDocument] = Field(default_factory=list)
    pinned: list[_PairDocument] = Field(default_factory=list)
    prohibited: list[_PairDocument] = Field(default_factory=list)
    together: list[list[StrictStr]] = Field(default_factory=list)
    separate: list[list[StrictStr]] = Field(default_factory=list)
    maximum_commute_seconds: _NonNegativeInt | None = None
    student_commute_limits: list[tuple[StrictStr, _NonNegativeInt]] = Field(default_factory=list)
    prior_assignments: list[_PairDocument] = Field(default_factory=list)


class _OptimizationDocument(_DocumentModel):
    objectives: list[ObjectiveKind] = Field(
        default_factory=lambda: list(OptimizationConfig().objectives)
    )
    commute_target_seconds: _NonNegativeInt = 30 * 60
    time_limit_seconds: _PositiveSeconds = 30.0
    allow_unassigned: StrictBool = False


class _StudentDraftDocument(_DocumentModel):
    key: StrictStr
    name: StrictStr = ""
    id: StrictStr = ""
    address: StrictStr = ""
    coordinates: StrictStr = ""


class _LocationDraftDocument(_DocumentModel):
    key: StrictStr
    name: StrictStr = ""
    id: StrictStr = ""
    capacity: StrictStr = ""
    minimum_capacity: StrictStr = ""
    address: StrictStr = ""
    coordinates: StrictStr = ""


class _ManualTimeDocument(_DocumentModel):
    student_key: StrictStr
    location_key: StrictStr
    value: StrictStr


class _ManualDistanceDocument(_DocumentModel):
    student_key: StrictStr
    location_key: StrictStr
    distance_meters: _NonNegativeInt


class _SavedDraftDocument(_DocumentModel):
    schema_version: Literal[1]
    document_kind: Literal["draft"]
    name: StrictStr = "Untitled placement"
    students: list[_StudentDraftDocument] = Field(default_factory=list)
    locations: list[_LocationDraftDocument] = Field(default_factory=list)
    rules: _RulesDocument = Field(default_factory=_RulesDocument)
    optimization: _OptimizationDocument = Field(default_factory=_OptimizationDocument)
    travel_mode: TravelMode = TravelMode.MANUAL
    manual_times: list[_ManualTimeDocument] = Field(default_factory=list)
    manual_distances_meters: list[_ManualDistanceDocument] = Field(default_factory=list)
    calculated_matrix: _TravelMatrixDocument | None = None
    calculated_travel_is_stale: StrictBool = False

    @model_validator(mode="after")
    def references_are_consistent(self) -> _SavedDraftDocument:
        student_keys = [student.key for student in self.students]
        location_keys = [location.key for location in self.locations]
        if len(set(student_keys)) != len(student_keys):
            raise ValueError("student row keys must be unique")
        if len(set(location_keys)) != len(location_keys):
            raise ValueError("location row keys must be unique")
        valid_students = set(student_keys)
        valid_locations = set(location_keys)
        time_keys = [(cell.student_key, cell.location_key) for cell in self.manual_times]
        distance_keys = [
            (cell.student_key, cell.location_key) for cell in self.manual_distances_meters
        ]
        if len(set(time_keys)) != len(time_keys) or len(set(distance_keys)) != len(distance_keys):
            raise ValueError("manual travel cells must be unique")
        if any(
            student_key not in valid_students or location_key not in valid_locations
            for student_key, location_key in [*time_keys, *distance_keys]
        ):
            raise ValueError("manual travel cell references an unknown row")
        matrix = self.calculated_matrix
        if matrix is not None:
            matrices = [matrix.durations_seconds]
            if matrix.distances_meters is not None:
                matrices.append(matrix.distances_meters)
            if any(
                len(values) != len(student_keys)
                or any(len(row) != len(location_keys) for row in values)
                for values in matrices
            ):
                raise ValueError("calculated travel dimensions do not match the draft")
        return self


class _ProjectDocument(_DocumentModel):
    schema_version: Literal[1]
    name: StrictStr = "Untitled placement"
    students: list[_StudentDocument] = Field(default_factory=list)
    locations: list[_LocationDocument] = Field(default_factory=list)
    travel_matrix: _TravelMatrixDocument | None = None
    rules: _RulesDocument = Field(default_factory=_RulesDocument)
    optimization: _OptimizationDocument = Field(default_factory=_OptimizationDocument)

    @model_validator(mode="after")
    def matrix_matches_entities(self) -> _ProjectDocument:
        matrix = self.travel_matrix
        if matrix is None:
            return self
        expected_rows = len(self.students)
        expected_columns = len(self.locations)
        matrices = [matrix.durations_seconds]
        if matrix.distances_meters is not None:
            matrices.append(matrix.distances_meters)
        for values in matrices:
            if len(values) != expected_rows or any(len(row) != expected_columns for row in values):
                raise ValueError("travel matrix dimensions do not match the project")
        return self


def save_project(project: PlacementProject, path: str | Path) -> None:
    _save_document(_to_document(project), path)


def save_draft_session(session: DraftSession, path: str | Path) -> None:
    """Save every raw draft row and partial travel cell without requiring validity."""

    _save_document(_draft_to_document(session), path)


def _save_document(document: dict[str, object], path: str | Path) -> None:
    target = Path(path)
    temporary_path: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except OSError as error:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise ProjectFileError(f"Could not save project: {error.strerror or error}") from error


def load_draft_session(path: str | Path) -> DraftSession:
    """Load a draft-aware file, with compatibility for earlier valid project files."""

    try:
        with Path(path).open(encoding="utf-8") as project_file:
            value = json.load(project_file)
        if isinstance(value, dict) and value.get("document_kind") == "draft":
            return _draft_from_document(value)
        return DraftSession.from_project(_from_document(value))
    except ProjectFileError:
        raise
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        raise ProjectFileError(
            "This project file could not be read. Start a new project or choose another file."
        ) from error


def load_project(path: str | Path) -> PlacementProject:
    try:
        with Path(path).open(encoding="utf-8") as project_file:
            document = json.load(project_file)
        return _from_document(document)
    except ProjectFileError:
        raise
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        raise ProjectFileError(
            "This project file could not be read. Start a new project or choose another file."
        ) from error


def _to_document(project: PlacementProject) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "name": project.name,
        "students": [_student_document(student) for student in project.students],
        "locations": [_location_document(location) for location in project.locations],
        "travel_matrix": (
            {
                "source": project.travel_matrix.source,
                "durations_seconds": project.travel_matrix.durations_seconds,
                "distances_meters": project.travel_matrix.distances_meters,
            }
            if project.travel_matrix is not None
            else None
        ),
        "rules": _rules_document(project.rules),
        "optimization": _optimization_document(project.optimization),
    }


def _draft_to_document(session: DraftSession) -> dict[str, object]:
    matrix = session.calculated_matrix
    if matrix is not None and (
        len(matrix.durations_seconds) != len(session.students)
        or len(matrix.distances_meters) != len(session.students)
        or any(len(row) != len(session.locations) for row in matrix.durations_seconds)
        or any(len(row) != len(session.locations) for row in matrix.distances_meters)
    ):
        # Structural roster edits leave keyed manual cells intact, but the old
        # positional provider matrix cannot be safely associated with new rows.
        matrix = None
    return {
        "schema_version": _SCHEMA_VERSION,
        "document_kind": "draft",
        "name": session.name,
        "students": [
            {
                "key": row.key,
                "name": row.name,
                "id": row.id,
                "address": row.address,
                "coordinates": row.coordinates,
            }
            for row in session.students
        ],
        "locations": [
            {
                "key": row.key,
                "name": row.name,
                "id": row.id,
                "capacity": row.capacity,
                "minimum_capacity": row.minimum_capacity,
                "address": row.address,
                "coordinates": row.coordinates,
            }
            for row in session.locations
        ],
        "rules": _rules_document(session.rules),
        "optimization": _optimization_document(session.optimization),
        "travel_mode": session.travel_mode.value,
        "manual_times": [
            {"student_key": key[0], "location_key": key[1], "value": value}
            for key, value in session.manual_times.items()
        ],
        "manual_distances_meters": [
            {
                "student_key": key[0],
                "location_key": key[1],
                "distance_meters": value,
            }
            for key, value in session.manual_distances_meters.items()
        ],
        "calculated_matrix": (
            {
                "source": matrix.source,
                "durations_seconds": matrix.durations_seconds,
                "distances_meters": matrix.distances_meters,
            }
            if matrix is not None
            else None
        ),
        "calculated_travel_is_stale": (
            session.calculated_travel_is_stale if matrix is not None else False
        ),
    }


def _draft_from_document(value: object) -> DraftSession:
    document = _SavedDraftDocument.model_validate(value)
    matrix = _travel_matrix_from_document(document.calculated_matrix)
    rules = _rules_from_document(document.rules)
    optimization = _optimization_from_document(document.optimization)
    return DraftSession.from_saved_draft(
        name=document.name,
        students=tuple(
            StudentDraft(
                key=row.key,
                name=row.name,
                id=row.id,
                address=row.address,
                coordinates=row.coordinates,
            )
            for row in document.students
        ),
        locations=tuple(
            LocationDraft(
                key=row.key,
                name=row.name,
                id=row.id,
                capacity=row.capacity,
                minimum_capacity=row.minimum_capacity,
                address=row.address,
                coordinates=row.coordinates,
            )
            for row in document.locations
        ),
        rules=rules,
        optimization=optimization,
        travel_mode=document.travel_mode,
        manual_times={
            (cell.student_key, cell.location_key): cell.value for cell in document.manual_times
        },
        manual_distances_meters={
            (cell.student_key, cell.location_key): cell.distance_meters
            for cell in document.manual_distances_meters
        },
        calculated_matrix=matrix,
        calculated_travel_is_stale=document.calculated_travel_is_stale,
    )


def _from_document(value: object) -> PlacementProject:
    document = _ProjectDocument.model_validate(value)
    travel_matrix = None
    if document.travel_matrix is not None:
        durations = tuple(tuple(row) for row in document.travel_matrix.durations_seconds)
        distances = (
            tuple(tuple(row) for row in document.travel_matrix.distances_meters)
            if document.travel_matrix.distances_meters is not None
            else tuple(tuple(None for _ in document.locations) for _ in document.students)
        )
        travel_matrix = TravelMatrix(
            distances_meters=distances,
            durations_seconds=durations,
            source=document.travel_matrix.source,
        )

    return PlacementProject(
        name=document.name,
        students=tuple(
            Student(
                id=item.id,
                name=item.name,
                address=item.address,
                coordinate=_coordinate_from_document(item.coordinate),
            )
            for item in document.students
        ),
        locations=tuple(
            Location(
                id=item.id,
                name=item.name,
                capacity=item.capacity,
                address=item.address,
                coordinate=_coordinate_from_document(item.coordinate),
                minimum_capacity=item.minimum_capacity,
            )
            for item in document.locations
        ),
        travel_matrix=travel_matrix,
        rules=AssignmentRules(
            eligible_locations=tuple(
                Preference(item.student_id, tuple(item.location_ids))
                for item in document.rules.eligible_locations
            ),
            preferences=tuple(
                Preference(item.student_id, tuple(item.location_ids))
                for item in document.rules.preferences
            ),
            pinned=tuple(
                StudentLocationPair(item.student_id, item.location_id)
                for item in document.rules.pinned
            ),
            prohibited=tuple(
                StudentLocationPair(item.student_id, item.location_id)
                for item in document.rules.prohibited
            ),
            together=tuple(
                GroupRule(tuple(student_ids)) for student_ids in document.rules.together
            ),
            separate=tuple(
                GroupRule(tuple(student_ids)) for student_ids in document.rules.separate
            ),
            maximum_commute_seconds=document.rules.maximum_commute_seconds,
            student_commute_limits=tuple(document.rules.student_commute_limits),
            prior_assignments=tuple(
                StudentLocationPair(item.student_id, item.location_id)
                for item in document.rules.prior_assignments
            ),
        ),
        optimization=OptimizationConfig(
            objectives=tuple(document.optimization.objectives),
            commute_target_seconds=document.optimization.commute_target_seconds,
            time_limit_seconds=document.optimization.time_limit_seconds,
            allow_unassigned=document.optimization.allow_unassigned,
        ),
    )


def _rules_document(rules: AssignmentRules) -> dict[str, object]:
    return {
        "eligible_locations": [_preference_document(item) for item in rules.eligible_locations],
        "preferences": [_preference_document(item) for item in rules.preferences],
        "pinned": [_pair_document(item) for item in rules.pinned],
        "prohibited": [_pair_document(item) for item in rules.prohibited],
        "together": [list(item.student_ids) for item in rules.together],
        "separate": [list(item.student_ids) for item in rules.separate],
        "maximum_commute_seconds": rules.maximum_commute_seconds,
        "student_commute_limits": rules.student_commute_limits,
        "prior_assignments": [_pair_document(item) for item in rules.prior_assignments],
    }


def _optimization_document(config: OptimizationConfig) -> dict[str, object]:
    return {
        "objectives": [objective.value for objective in config.objectives],
        "commute_target_seconds": config.commute_target_seconds,
        "time_limit_seconds": config.time_limit_seconds,
        "allow_unassigned": config.allow_unassigned,
    }


def _rules_from_document(document: _RulesDocument) -> AssignmentRules:
    return AssignmentRules(
        eligible_locations=tuple(
            Preference(item.student_id, tuple(item.location_ids))
            for item in document.eligible_locations
        ),
        preferences=tuple(
            Preference(item.student_id, tuple(item.location_ids)) for item in document.preferences
        ),
        pinned=tuple(
            StudentLocationPair(item.student_id, item.location_id) for item in document.pinned
        ),
        prohibited=tuple(
            StudentLocationPair(item.student_id, item.location_id) for item in document.prohibited
        ),
        together=tuple(GroupRule(tuple(student_ids)) for student_ids in document.together),
        separate=tuple(GroupRule(tuple(student_ids)) for student_ids in document.separate),
        maximum_commute_seconds=document.maximum_commute_seconds,
        student_commute_limits=tuple(document.student_commute_limits),
        prior_assignments=tuple(
            StudentLocationPair(item.student_id, item.location_id)
            for item in document.prior_assignments
        ),
    )


def _optimization_from_document(document: _OptimizationDocument) -> OptimizationConfig:
    return OptimizationConfig(
        objectives=tuple(document.objectives),
        commute_target_seconds=document.commute_target_seconds,
        time_limit_seconds=document.time_limit_seconds,
        allow_unassigned=document.allow_unassigned,
    )


def _travel_matrix_from_document(
    document: _TravelMatrixDocument | None,
) -> TravelMatrix | None:
    if document is None:
        return None
    durations = tuple(tuple(row) for row in document.durations_seconds)
    distances = (
        tuple(tuple(row) for row in document.distances_meters)
        if document.distances_meters is not None
        else tuple(tuple(None for _ in row) for row in durations)
    )
    return TravelMatrix(distances, durations, document.source)


def _student_document(student: Student) -> dict[str, object]:
    return {
        "id": student.id,
        "name": student.name,
        "address": student.address,
        "coordinate": _coordinate_document(student.coordinate),
    }


def _location_document(location: Location) -> dict[str, object]:
    return {
        "id": location.id,
        "name": location.name,
        "capacity": location.capacity,
        "minimum_capacity": location.minimum_capacity,
        "address": location.address,
        "coordinate": _coordinate_document(location.coordinate),
    }


def _coordinate_document(coordinate: Coordinate | None) -> dict[str, float] | None:
    if coordinate is None:
        return None
    return {"latitude": coordinate.latitude, "longitude": coordinate.longitude}


def _coordinate_from_document(value: _CoordinateDocument | None) -> Coordinate | None:
    if value is None:
        return None
    return Coordinate(value.latitude, value.longitude)


def _preference_document(value: Preference) -> dict[str, object]:
    return {"student_id": value.student_id, "location_ids": list(value.location_ids)}


def _pair_document(value: StudentLocationPair) -> dict[str, str]:
    return {"student_id": value.student_id, "location_id": value.location_id}
