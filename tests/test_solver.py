from __future__ import annotations

import pytest

from placement_optimizer import (
    AssignmentProblem,
    InfeasibleAssignmentError,
    Location,
    Objective,
    ProblemValidationError,
    Student,
    solve_assignment,
)


def problem(
    distances: tuple[tuple[int | None, ...], ...],
    capacities: tuple[int, ...],
) -> AssignmentProblem:
    return AssignmentProblem(
        students=tuple(Student(f"s{i + 1}", f"Student {i + 1}") for i in range(len(distances))),
        locations=tuple(
            Location(f"l{i + 1}", f"Location {i + 1}", capacity)
            for i, capacity in enumerate(capacities)
        ),
        distances_meters=distances,
    )


def assignments_by_student(result):
    return {assignment.student_id: assignment.location_id for assignment in result.assignments}


def test_total_distance_finds_global_optimum_with_capacities() -> None:
    # Greedily assigning s1 to l1 would force s2 into a very long journey.
    result = solve_assignment(
        problem(((1, 2), (2, 100)), (1, 1)),
        Objective.TOTAL_DISTANCE,
    )

    assert assignments_by_student(result) == {"s1": "l2", "s2": "l1"}
    assert result.total_distance_meters == 4
    assert result.maximum_distance_meters == 2


def test_fair_objective_minimizes_worst_trip_before_total() -> None:
    placement = problem(
        (
            (1, 6),
            (2, 6),
            (3, 100),
        ),
        (2, 1),
    )

    total = solve_assignment(placement, Objective.TOTAL_DISTANCE)
    fair = solve_assignment(placement, Objective.FAIR_DISTANCE)

    assert total.total_distance_meters == 10
    assert total.maximum_distance_meters == 6
    assert fair.maximum_distance_meters == 6
    assert fair.total_distance_meters == 10


def test_fair_objective_can_trade_total_distance_for_a_shorter_worst_trip() -> None:
    placement = problem(
        (
            (1, 10),
            (15, 20),
        ),
        (1, 1),
    )

    total = solve_assignment(placement, Objective.TOTAL_DISTANCE)
    fair = solve_assignment(placement, Objective.FAIR_DISTANCE)

    assert total.total_distance_meters == 21
    assert total.maximum_distance_meters == 20
    assert fair.total_distance_meters == 25
    assert fair.maximum_distance_meters == 15


def test_unavailable_routes_are_never_selected() -> None:
    result = solve_assignment(problem(((None, 4), (2, None)), (1, 1)))
    assert assignments_by_student(result) == {"s1": "l2", "s2": "l1"}


def test_capacity_shortfall_has_clear_error() -> None:
    with pytest.raises(InfeasibleAssignmentError, match="total location capacity"):
        solve_assignment(problem(((1,), (2,)), (1,)))


def test_student_without_any_route_is_reported() -> None:
    placement = problem(((1, 2), (None, None)), (1, 1))
    with pytest.raises(InfeasibleAssignmentError) as error:
        solve_assignment(placement)
    assert error.value.student_ids == ("s2",)


def test_route_capacity_bottleneck_is_reported() -> None:
    placement = problem(((1, None), (2, None)), (1, 1))
    with pytest.raises(InfeasibleAssignmentError, match="available road routes"):
        solve_assignment(placement)


def test_reference_solver_rejects_minimum_capacities_it_cannot_model() -> None:
    placement = problem(((1,),), (1,))
    placement = AssignmentProblem(
        students=placement.students,
        locations=(Location("l1", "Location", 1, minimum_capacity=1),),
        distances_meters=placement.distances_meters,
    )
    with pytest.raises(ProblemValidationError, match="does not support minimum"):
        solve_assignment(placement)


def test_matrix_shape_is_validated() -> None:
    with pytest.raises(ProblemValidationError, match="one column"):
        solve_assignment(problem(((1,),), (1, 1)))


def test_empty_problem_is_valid() -> None:
    result = solve_assignment(problem((), (3,)))
    assert result.assignments == ()
    assert result.average_distance_meters == 0
    assert result.location_utilization[0].assigned == 0


def test_duration_is_carried_to_assignment() -> None:
    placement = problem(((1200,),), (1,))
    placement = AssignmentProblem(
        students=placement.students,
        locations=placement.locations,
        distances_meters=placement.distances_meters,
        durations_seconds=((300,),),
    )
    result = solve_assignment(placement)
    assert result.assignments[0].duration_seconds == 300
