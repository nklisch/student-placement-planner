"""Application-level solve orchestration and recoverable outcome mapping."""

from __future__ import annotations

from placement_optimizer.application.models import (
    OutcomeKind,
    PlacementProject,
    SolveProjectOutcome,
)
from placement_optimizer.optimization import (
    OptimizationCancellation,
    OptimizationInputError,
    OptimizationProblem,
    SolveProof,
    solve_optimization_problem,
)


def solve_project(
    project: PlacementProject,
    cancellation: OptimizationCancellation | None = None,
) -> SolveProjectOutcome:
    """Solve a ready project without exposing routine failures as exceptions."""

    if cancellation is not None and cancellation.is_cancelled:
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "The calculation was cancelled.")
    if not project.students:
        return SolveProjectOutcome(
            OutcomeKind.NEEDS_ATTENTION,
            "Add at least one student before optimizing.",
        )
    if not project.locations:
        return SolveProjectOutcome(
            OutcomeKind.NEEDS_ATTENTION,
            "Add at least one placement location before optimizing.",
        )
    if project.travel_matrix is None:
        return SolveProjectOutcome(
            OutcomeKind.NEEDS_ATTENTION,
            "Add driving times using a map mode or the manual travel-time table.",
        )

    try:
        result = solve_optimization_problem(
            OptimizationProblem(
                students=project.students,
                locations=project.locations,
                durations_seconds=project.travel_matrix.durations_seconds,
                distances_meters=project.travel_matrix.distances_meters,
                rules=project.rules,
                config=project.optimization,
            ),
            cancellation,
        )
    except OptimizationInputError as error:
        return SolveProjectOutcome(OutcomeKind.INVALID, str(error))

    if cancellation is not None and cancellation.is_cancelled:
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "The calculation was cancelled.")
    if result.proof is SolveProof.INFEASIBLE:
        return SolveProjectOutcome(OutcomeKind.INFEASIBLE, result.message, result)
    if result.proof is SolveProof.NOT_SOLVED:
        return SolveProjectOutcome(OutcomeKind.NOT_SOLVED, result.message, result)
    if result.unassigned_student_ids or result.proof is SolveProof.FEASIBLE:
        return SolveProjectOutcome(OutcomeKind.NEEDS_ATTENTION, result.message, result)
    return SolveProjectOutcome(OutcomeKind.SUCCESS, result.message, result)
