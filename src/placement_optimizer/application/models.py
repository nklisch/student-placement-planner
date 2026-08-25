"""Project and workflow result types consumed by the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from placement_optimizer.domain import Location, Student
from placement_optimizer.optimization import (
    AssignmentRules,
    OptimizationConfig,
    OptimizationResult,
)
from placement_optimizer.travel import TravelMatrix


@dataclass(frozen=True, slots=True)
class PlacementProject:
    name: str = "Untitled placement"
    students: tuple[Student, ...] = ()
    locations: tuple[Location, ...] = ()
    travel_matrix: TravelMatrix | None = None
    rules: AssignmentRules = field(default_factory=AssignmentRules)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)


class OutcomeKind(StrEnum):
    SUCCESS = "success"
    NEEDS_ATTENTION = "needs_attention"
    INFEASIBLE = "infeasible"
    NOT_SOLVED = "not_solved"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SolveProjectOutcome:
    kind: OutcomeKind
    message: str
    result: OptimizationResult | None = None
