from __future__ import annotations

from itertools import product

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ortools.sat.python import cp_model

from placement_optimizer.domain import AssignmentProblem, Location, Objective, Student
from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    ObjectiveKind,
    OptimizationConfig,
    OptimizationInputError,
    OptimizationProblem,
    Preference,
    SolveProof,
    StudentLocationPair,
    solve_optimization_problem,
)
from placement_optimizer.optimization import ortools_solver as solver_module
from placement_optimizer.solver import solve_assignment


def make_problem(
    durations: tuple[tuple[int | None, ...], ...],
    capacities: tuple[int, ...],
    *,
    rules: AssignmentRules | None = None,
    objectives: tuple[ObjectiveKind, ...] = (
        ObjectiveKind.MAXIMUM_COMMUTE,
        ObjectiveKind.TOTAL_COMMUTE,
    ),
    allow_unassigned: bool = False,
    minimum_capacities: tuple[int, ...] | None = None,
    commute_target_seconds: int = 30 * 60,
) -> OptimizationProblem:
    minimum_capacities = minimum_capacities or (0,) * len(capacities)
    return OptimizationProblem(
        students=tuple(Student(f"s{i + 1}", f"Student {i + 1}") for i in range(len(durations))),
        locations=tuple(
            Location(
                f"l{i + 1}",
                f"Location {i + 1}",
                capacity,
                minimum_capacity=minimum_capacities[i],
            )
            for i, capacity in enumerate(capacities)
        ),
        durations_seconds=durations,
        distances_meters=tuple(
            tuple(None if value is None else value * 10 for value in row) for row in durations
        ),
        rules=rules or AssignmentRules(),
        config=OptimizationConfig(
            objectives=objectives,
            allow_unassigned=allow_unassigned,
            commute_target_seconds=commute_target_seconds,
            time_limit_seconds=10,
        ),
    )


def by_student(result):
    return {placement.student_id: placement.location_id for placement in result.placements}


def test_ordered_objectives_change_the_selected_assignment() -> None:
    durations = ((1, 10), (15, 20))
    total = solve_optimization_problem(
        make_problem(durations, (1, 1), objectives=(ObjectiveKind.TOTAL_COMMUTE,))
    )
    fair = solve_optimization_problem(
        make_problem(
            durations,
            (1, 1),
            objectives=(ObjectiveKind.MAXIMUM_COMMUTE, ObjectiveKind.TOTAL_COMMUTE),
        )
    )

    assert total.proof is SolveProof.OPTIMAL
    assert total.total_commute_seconds == 21
    assert total.maximum_commute_seconds == 20
    assert fair.total_commute_seconds == 25
    assert fair.maximum_commute_seconds == 15


def test_eligibility_prohibitions_and_pins_are_hard_rules() -> None:
    rules = AssignmentRules(
        eligible_locations=(Preference("s1", ("l1",)),),
        prohibited=(StudentLocationPair("s2", "l1"),),
        pinned=(StudentLocationPair("s3", "l1"),),
    )
    result = solve_optimization_problem(make_problem(((1, 2), (1, 2), (9, 1)), (2, 2), rules=rules))

    assert result.proof is SolveProof.OPTIMAL
    assert by_student(result) == {"s1": "l1", "s2": "l2", "s3": "l1"}


def test_preferences_can_be_the_primary_goal() -> None:
    rules = AssignmentRules(
        preferences=(
            Preference("s1", ("l2", "l1")),
            Preference("s2", ("l1", "l2")),
        )
    )
    result = solve_optimization_problem(
        make_problem(
            ((1, 20), (20, 1)),
            (1, 1),
            rules=rules,
            objectives=(ObjectiveKind.PREFERENCE_PENALTY, ObjectiveKind.TOTAL_COMMUTE),
        )
    )

    assert by_student(result) == {"s1": "l2", "s2": "l1"}
    assert [placement.preference_rank for placement in result.placements] == [1, 1]


def test_global_and_per_student_commute_limits_remove_edges() -> None:
    rules = AssignmentRules(
        maximum_commute_seconds=15,
        student_commute_limits=(("s2", 8),),
    )
    result = solve_optimization_problem(make_problem(((10, 20), (9, 7)), (1, 1), rules=rules))
    assert by_student(result) == {"s1": "l1", "s2": "l2"}


def test_together_group_uses_the_same_location() -> None:
    rules = AssignmentRules(together=(GroupRule(("s1", "s2")),))
    result = solve_optimization_problem(make_problem(((1, 2), (2, 1)), (2, 2), rules=rules))
    selected = by_student(result)
    assert selected["s1"] == selected["s2"]


def test_separate_group_cannot_share_a_location() -> None:
    rules = AssignmentRules(separate=(GroupRule(("s1", "s2")),))
    result = solve_optimization_problem(make_problem(((1, 20), (1, 20)), (2, 2), rules=rules))
    selected = by_student(result)
    assert selected["s1"] != selected["s2"]


def test_minimum_capacity_is_respected() -> None:
    result = solve_optimization_problem(
        make_problem(((1, 2), (1, 2)), (2, 2), minimum_capacities=(0, 1))
    )
    assert dict(result.location_counts)["l2"] >= 1


def test_capacity_shortfall_can_return_an_explicit_unassigned_student() -> None:
    result = solve_optimization_problem(make_problem(((1,), (2,)), (1,), allow_unassigned=True))
    assert result.proof is SolveProof.OPTIMAL
    assert len(result.unassigned_student_ids) == 1
    assert len(result.placements) == 2


def test_capacity_shortfall_is_actionable_when_unassigned_is_disabled() -> None:
    result = solve_optimization_problem(make_problem(((1,), (2,)), (1,)))
    assert result.proof is SolveProof.INFEASIBLE
    assert "available placement spaces" in result.message


def test_impossible_pin_returns_infeasible_instead_of_crashing() -> None:
    rules = AssignmentRules(
        pinned=(StudentLocationPair("s1", "l2"),),
        prohibited=(StudentLocationPair("s1", "l2"),),
    )
    result = solve_optimization_problem(make_problem(((1, 2),), (1, 1), rules=rules))
    assert result.proof is SolveProof.INFEASIBLE


def test_over_target_count_can_precede_total_commute() -> None:
    result = solve_optimization_problem(
        make_problem(
            ((11, 50), (1, 11)),
            (1, 1),
            objectives=(ObjectiveKind.OVER_TARGET_COUNT, ObjectiveKind.TOTAL_COMMUTE),
            commute_target_seconds=10,
        )
    )
    assert by_student(result) == {"s1": "l2", "s2": "l1"}
    assert result.total_commute_seconds == 51


def test_assignment_change_objective_can_preserve_prior_placements() -> None:
    rules = AssignmentRules(
        prior_assignments=(
            StudentLocationPair("s1", "l2"),
            StudentLocationPair("s2", "l1"),
        )
    )
    result = solve_optimization_problem(
        make_problem(
            ((1, 20), (20, 1)),
            (1, 1),
            rules=rules,
            objectives=(ObjectiveKind.ASSIGNMENT_CHANGES, ObjectiveKind.TOTAL_COMMUTE),
        )
    )
    assert by_student(result) == {"s1": "l2", "s2": "l1"}
    assert all(not placement.changed_from_prior for placement in result.placements)


def test_prior_assignment_change_is_reported() -> None:
    rules = AssignmentRules(
        prior_assignments=(StudentLocationPair("s1", "l2"),),
    )
    result = solve_optimization_problem(
        make_problem(((1, 20),), (1, 1), rules=rules, objectives=(ObjectiveKind.TOTAL_COMMUTE,))
    )
    assert result.placements[0].changed_from_prior is True


def test_tied_problem_is_deterministic() -> None:
    problem = make_problem(((10, 10), (10, 10)), (1, 1))
    outputs = [by_student(solve_optimization_problem(problem)) for _ in range(5)]
    assert outputs == [outputs[0]] * 5


def test_unknown_solver_status_is_a_recoverable_not_solved_result(monkeypatch) -> None:
    class UnknownSolver:
        def solve(self, model) -> int:
            return cp_model.UNKNOWN

    monkeypatch.setattr(solver_module, "_configured_solver", lambda remaining: UnknownSolver())
    result = solve_optimization_problem(make_problem(((1,),), (1,)))
    assert result.proof is SolveProof.NOT_SOLVED
    assert "Try again" in result.message


def test_advanced_and_reference_solvers_agree_on_simple_fair_problem() -> None:
    durations = ((9, 3), (4, 8), (7, 6))
    advanced_problem = make_problem(durations, (2, 1))
    advanced = solve_optimization_problem(advanced_problem)
    reference = solve_assignment(
        AssignmentProblem(
            students=advanced_problem.students,
            locations=advanced_problem.locations,
            distances_meters=durations,
        ),
        Objective.FAIR_DISTANCE,
    )
    assert advanced.maximum_commute_seconds == reference.maximum_distance_meters
    assert advanced.total_commute_seconds == reference.total_distance_meters


def test_invalid_rule_reference_is_rejected() -> None:
    rules = AssignmentRules(pinned=(StudentLocationPair("missing", "l1"),))
    with pytest.raises(OptimizationInputError, match="unknown student"):
        solve_optimization_problem(make_problem(((1,),), (1,), rules=rules))


@settings(max_examples=50, deadline=None)
@given(
    student_count=st.integers(min_value=1, max_value=5),
    location_count=st.integers(min_value=1, max_value=4),
    data=st.data(),
)
def test_simple_models_match_exhaustive_enumeration(
    student_count: int,
    location_count: int,
    data: st.DataObject,
) -> None:
    capacities = tuple(
        data.draw(st.integers(min_value=0, max_value=student_count), label=f"capacity-{j}")
        for j in range(location_count)
    )
    durations = tuple(
        tuple(
            data.draw(
                st.one_of(st.none(), st.integers(min_value=0, max_value=50)),
                label=f"duration-{i}-{j}",
            )
            for j in range(location_count)
        )
        for i in range(student_count)
    )
    assignment_options = []
    for assignment in product(range(location_count), repeat=student_count):
        if any(assignment.count(j) > capacities[j] for j in range(location_count)):
            continue
        selected = [durations[i][assignment[i]] for i in range(student_count)]
        if any(value is None for value in selected):
            continue
        numeric = [value for value in selected if value is not None]
        assignment_options.append((max(numeric), sum(numeric)))

    result = solve_optimization_problem(make_problem(durations, capacities))
    if not assignment_options:
        assert result.proof is SolveProof.INFEASIBLE
    else:
        assert result.proof is SolveProof.OPTIMAL
        assert (result.maximum_commute_seconds, result.total_commute_seconds) == min(
            assignment_options
        )
