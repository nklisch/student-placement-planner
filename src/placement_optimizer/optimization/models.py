"""Typed inputs and outputs for the configurable placement model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from placement_optimizer.domain import Location, Student


@dataclass(frozen=True, slots=True)
class StudentLocationPair:
    student_id: str
    location_id: str


@dataclass(frozen=True, slots=True)
class Preference:
    """Location IDs for one student, ordered from most to least preferred."""

    student_id: str
    location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroupRule:
    """A group participating in either a together or separate rule."""

    student_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssignmentRules:
    """Optional hard constraints and preference data.

    An omitted eligibility entry means that student may use any location.
    An eligibility entry with an empty location tuple means no location is
    eligible and will produce an actionable infeasible result.
    """

    eligible_locations: tuple[Preference, ...] = ()
    preferences: tuple[Preference, ...] = ()
    pinned: tuple[StudentLocationPair, ...] = ()
    prohibited: tuple[StudentLocationPair, ...] = ()
    together: tuple[GroupRule, ...] = ()
    separate: tuple[GroupRule, ...] = ()
    maximum_commute_seconds: int | None = None
    student_commute_limits: tuple[tuple[str, int], ...] = ()
    prior_assignments: tuple[StudentLocationPair, ...] = ()


class ObjectiveKind(StrEnum):
    UNASSIGNED_COUNT = "unassigned_count"
    MAXIMUM_COMMUTE = "maximum_commute"
    OVER_TARGET_COUNT = "over_target_count"
    TOTAL_COMMUTE = "total_commute"
    PREFERENCE_PENALTY = "preference_penalty"
    ASSIGNMENT_CHANGES = "assignment_changes"


FAIR_COMMUTE_OBJECTIVES = (
    ObjectiveKind.MAXIMUM_COMMUTE,
    ObjectiveKind.OVER_TARGET_COUNT,
    ObjectiveKind.TOTAL_COMMUTE,
    ObjectiveKind.PREFERENCE_PENALTY,
)

LOWEST_TOTAL_OBJECTIVES = (
    ObjectiveKind.TOTAL_COMMUTE,
    ObjectiveKind.MAXIMUM_COMMUTE,
    ObjectiveKind.PREFERENCE_PENALTY,
)

CHOICES_FIRST_OBJECTIVES = (
    ObjectiveKind.PREFERENCE_PENALTY,
    ObjectiveKind.MAXIMUM_COMMUTE,
    ObjectiveKind.TOTAL_COMMUTE,
)


@dataclass(frozen=True, slots=True)
class OptimizationConfig:
    objectives: tuple[ObjectiveKind, ...] = FAIR_COMMUTE_OBJECTIVES
    commute_target_seconds: int = 30 * 60
    time_limit_seconds: float = 30.0
    allow_unassigned: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    students: tuple[Student, ...]
    locations: tuple[Location, ...]
    # Rows are students, columns are locations. None means no road route.
    durations_seconds: tuple[tuple[int | None, ...], ...]
    distances_meters: tuple[tuple[int | None, ...], ...] | None = None
    rules: AssignmentRules = field(default_factory=AssignmentRules)
    config: OptimizationConfig = field(default_factory=OptimizationConfig)


class SolveProof(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    NOT_SOLVED = "not_solved"


@dataclass(frozen=True, slots=True)
class Placement:
    student_id: str
    location_id: str | None
    duration_seconds: int | None
    distance_meters: int | None
    preference_rank: int | None
    changed_from_prior: bool


@dataclass(frozen=True, slots=True)
class OptimizationMetric:
    objective: ObjectiveKind
    value: int


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    proof: SolveProof
    placements: tuple[Placement, ...]
    metrics: tuple[OptimizationMetric, ...]
    total_commute_seconds: int
    maximum_commute_seconds: int
    average_commute_seconds: float
    unassigned_student_ids: tuple[str, ...]
    location_counts: tuple[tuple[str, int], ...]
    message: str
