"""Local-first student placement optimization."""

from placement_optimizer.domain import (
    Assignment,
    AssignmentProblem,
    AssignmentResult,
    Coordinate,
    Location,
    Objective,
    Student,
)
from placement_optimizer.solver import (
    InfeasibleAssignmentError,
    ProblemValidationError,
    solve_assignment,
)

__all__ = [
    "Assignment",
    "AssignmentProblem",
    "AssignmentResult",
    "Coordinate",
    "InfeasibleAssignmentError",
    "Location",
    "Objective",
    "ProblemValidationError",
    "Student",
    "solve_assignment",
]
