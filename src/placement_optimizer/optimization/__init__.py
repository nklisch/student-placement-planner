"""Advanced placement optimization powered by OR-Tools."""

from placement_optimizer.optimization.models import (
    CHOICES_FIRST_OBJECTIVES,
    FAIR_COMMUTE_OBJECTIVES,
    LOWEST_TOTAL_OBJECTIVES,
    AssignmentRules,
    GroupRule,
    ObjectiveKind,
    OptimizationConfig,
    OptimizationMetric,
    OptimizationProblem,
    OptimizationResult,
    Placement,
    Preference,
    SolveProof,
    StudentLocationPair,
)
from placement_optimizer.optimization.ortools_solver import (
    OptimizationCancellation,
    OptimizationInputError,
    solve_optimization_problem,
)

__all__ = [
    "CHOICES_FIRST_OBJECTIVES",
    "FAIR_COMMUTE_OBJECTIVES",
    "LOWEST_TOTAL_OBJECTIVES",
    "AssignmentRules",
    "GroupRule",
    "ObjectiveKind",
    "OptimizationCancellation",
    "OptimizationConfig",
    "OptimizationInputError",
    "OptimizationMetric",
    "OptimizationProblem",
    "OptimizationResult",
    "Placement",
    "Preference",
    "SolveProof",
    "StudentLocationPair",
    "solve_optimization_problem",
]
