"""Configurable exact placement model using OR-Tools CP-SAT."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from time import monotonic

from ortools.sat.python import cp_model

from placement_optimizer.optimization.models import (
    ObjectiveKind,
    OptimizationConfig,
    OptimizationMetric,
    OptimizationProblem,
    OptimizationResult,
    Placement,
    Preference,
    SolveProof,
)


class OptimizationInputError(ValueError):
    """The model definition is inconsistent and must be corrected before solving."""


class OptimizationCancellation:
    """Thread-safe cancellation handle for the currently active OR-Tools search."""

    def __init__(self) -> None:
        self._cancelled = Event()
        self._lock = Lock()
        self._solver: cp_model.CpSolver | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            solver = self._solver
        if solver is not None:
            solver.stop_search()

    def _attach(self, solver: cp_model.CpSolver) -> None:
        with self._lock:
            if not self._cancelled.is_set():
                self._solver = solver
                return
        solver.stop_search()

    def _detach(self, solver: cp_model.CpSolver) -> None:
        with self._lock:
            if self._solver is solver:
                self._solver = None


@dataclass(slots=True)
class _BuiltModel:
    model: cp_model.CpModel
    assignment_variables: dict[tuple[int, int], cp_model.IntVar]
    unassigned_variables: dict[int, cp_model.IntVar]
    objective_expressions: dict[ObjectiveKind, cp_model.LinearExpr | int]
    preferences: dict[str, tuple[str, ...]]
    prior_assignments: dict[str, str]


def solve_optimization_problem(
    problem: OptimizationProblem,
    cancellation: OptimizationCancellation | None = None,
) -> OptimizationResult:
    """Solve configured priorities lexicographically.

    Every priority is proven and fixed before the next priority is considered.
    If the shared time budget expires after at least one solve, the last usable
    assignment is returned as FEASIBLE rather than discarding the user's work.
    """

    _validate(problem)
    if not problem.students:
        return _empty_result(problem)

    if not problem.config.allow_unassigned and sum(
        location.capacity for location in problem.locations
    ) < len(problem.students):
        return _infeasible_result(
            problem,
            "There are more students than available placement spaces. Increase capacity or "
            "enable unassigned results.",
        )

    built, unavailable_students = _build_model(problem)
    if unavailable_students and not problem.config.allow_unassigned:
        joined = ", ".join(unavailable_students)
        return _infeasible_result(
            problem,
            f"No permitted road route is available for: {joined}. Review addresses, eligibility, "
            "prohibited placements, or commute limits.",
        )

    objective_order = _objective_order(problem.config)
    if not objective_order:
        objective_order = (None,)

    started = monotonic()
    last_solver: cp_model.CpSolver | None = None
    metrics: list[OptimizationMetric] = []
    all_priorities_proven = True

    for objective in objective_order:
        if cancellation is not None and cancellation.is_cancelled:
            all_priorities_proven = False
            break
        remaining = problem.config.time_limit_seconds - (monotonic() - started)
        if remaining <= 0:
            all_priorities_proven = False
            break

        expression: cp_model.LinearExpr | int = (
            0 if objective is None else built.objective_expressions[objective]
        )
        built.model.minimize(expression)
        solver = _configured_solver(remaining)
        if cancellation is not None:
            cancellation._attach(solver)
        try:
            status = solver.solve(built.model)
        finally:
            if cancellation is not None:
                cancellation._detach(solver)

        if status == cp_model.INFEASIBLE:
            if last_solver is not None:
                raise RuntimeError(
                    "a previously feasible model became infeasible after fixing its optimum"
                )
            return _infeasible_result(
                problem,
                "No assignment satisfies all capacities and rules. Review commute limits, "
                "eligibility, pinned placements, and group rules.",
            )
        if status == cp_model.MODEL_INVALID:
            raise RuntimeError("OR-Tools rejected a validated placement model")
        if status == cp_model.UNKNOWN:
            all_priorities_proven = False
            break

        last_solver = solver
        if objective is not None:
            value = _expression_value(solver, expression)
            metrics.append(OptimizationMetric(objective, value))

        if status == cp_model.OPTIMAL:
            built.model.add(expression == _expression_value(solver, expression))
        else:
            all_priorities_proven = False
            break

    if last_solver is None:
        return OptimizationResult(
            proof=SolveProof.NOT_SOLVED,
            placements=(),
            metrics=(),
            total_commute_seconds=0,
            maximum_commute_seconds=0,
            average_commute_seconds=0.0,
            unassigned_student_ids=(),
            location_counts=tuple((location.id, 0) for location in problem.locations),
            message=(
                "No usable assignment was found within the time limit. Try again with a longer "
                "limit or fewer optional rules."
            ),
        )

    return _result_from_solution(
        problem,
        built,
        last_solver,
        tuple(metrics),
        optimal=all_priorities_proven,
    )


def _build_model(problem: OptimizationProblem) -> tuple[_BuiltModel, tuple[str, ...]]:
    model = cp_model.CpModel()
    student_indexes = {student.id: index for index, student in enumerate(problem.students)}
    location_indexes = {location.id: index for index, location in enumerate(problem.locations)}
    eligible = _preference_map(problem.rules.eligible_locations)
    preferences = _preference_map(problem.rules.preferences)
    prohibited = {(pair.student_id, pair.location_id) for pair in problem.rules.prohibited}
    commute_limits = dict(problem.rules.student_commute_limits)

    assignment_variables: dict[tuple[int, int], cp_model.IntVar] = {}
    unassigned_variables: dict[int, cp_model.IntVar] = {}
    unavailable_students: list[str] = []

    for student_index, student in enumerate(problem.students):
        student_variables: list[cp_model.IntVar] = []
        limit = commute_limits.get(student.id, problem.rules.maximum_commute_seconds)
        eligible_ids = set(eligible[student.id]) if student.id in eligible else None
        for location_index, location in enumerate(problem.locations):
            duration = problem.durations_seconds[student_index][location_index]
            permitted = (
                duration is not None
                and (eligible_ids is None or location.id in eligible_ids)
                and (student.id, location.id) not in prohibited
                and (limit is None or duration <= limit)
            )
            if not permitted:
                continue
            variable = model.new_bool_var(f"assign_s{student_index}_l{location_index}")
            assignment_variables[student_index, location_index] = variable
            student_variables.append(variable)

        if problem.config.allow_unassigned:
            unassigned = model.new_bool_var(f"unassigned_s{student_index}")
            unassigned_variables[student_index] = unassigned
            model.add(sum(student_variables) + unassigned == 1)
        else:
            model.add(sum(student_variables) == 1)
            if not student_variables:
                unavailable_students.append(student.id)

    for location_index, location in enumerate(problem.locations):
        variables = [
            assignment_variables[student_index, location_index]
            for student_index in range(len(problem.students))
            if (student_index, location_index) in assignment_variables
        ]
        model.add(sum(variables) <= location.capacity)
        if location.minimum_capacity:
            model.add(sum(variables) >= location.minimum_capacity)

    for pair in problem.rules.pinned:
        student_index = student_indexes[pair.student_id]
        location_index = location_indexes[pair.location_id]
        variable = assignment_variables.get((student_index, location_index))
        if variable is None:
            # An impossible pin makes the model infeasible without inventing an edge.
            model.add(0 == 1)
        else:
            model.add(variable == 1)

    for group in problem.rules.together:
        member_indexes = [student_indexes[student_id] for student_id in group.student_ids]
        reference = member_indexes[0]
        for member in member_indexes[1:]:
            for location_index in range(len(problem.locations)):
                model.add(
                    assignment_variables.get((reference, location_index), 0)
                    == assignment_variables.get((member, location_index), 0)
                )
            if problem.config.allow_unassigned:
                model.add(unassigned_variables[reference] == unassigned_variables[member])

    for group in problem.rules.separate:
        member_indexes = [student_indexes[student_id] for student_id in group.student_ids]
        for location_index in range(len(problem.locations)):
            variables = [
                assignment_variables[member_index, location_index]
                for member_index in member_indexes
                if (member_index, location_index) in assignment_variables
            ]
            if len(variables) > 1:
                model.add(sum(variables) <= 1)

    maximum_duration = max(
        (duration for row in problem.durations_seconds for duration in row if duration is not None),
        default=0,
    )
    maximum_commute = model.new_int_var(0, maximum_duration, "maximum_commute")
    for (student_index, location_index), variable in assignment_variables.items():
        duration = problem.durations_seconds[student_index][location_index]
        if duration is None:  # Variables are only created for available routes.
            raise RuntimeError("assignment variable exists for an unavailable route")
        model.add(maximum_commute >= duration).only_enforce_if(variable)

    preference_penalties: list[cp_model.LinearExpr] = []
    for (student_index, location_index), variable in assignment_variables.items():
        student_id = problem.students[student_index].id
        location_id = problem.locations[location_index].id
        choices = preferences.get(student_id)
        if choices is None:
            continue
        try:
            penalty = choices.index(location_id)
        except ValueError:
            penalty = len(choices)
        if penalty:
            preference_penalties.append(variable * penalty)

    prior_assignments = {
        pair.student_id: pair.location_id for pair in problem.rules.prior_assignments
    }
    change_terms: list[cp_model.LinearExpr | int] = []
    for student_index, student in enumerate(problem.students):
        previous_location_id = prior_assignments.get(student.id)
        if previous_location_id is None:
            continue
        previous_index = location_indexes[previous_location_id]
        previous_variable = assignment_variables.get((student_index, previous_index))
        change_terms.append(1 if previous_variable is None else 1 - previous_variable)

    objective_expressions: dict[ObjectiveKind, cp_model.LinearExpr | int] = {
        ObjectiveKind.UNASSIGNED_COUNT: sum(unassigned_variables.values()),
        ObjectiveKind.MAXIMUM_COMMUTE: maximum_commute,
        ObjectiveKind.OVER_TARGET_COUNT: sum(
            variable
            for (student_index, location_index), variable in assignment_variables.items()
            if _required_duration(problem, student_index, location_index)
            > problem.config.commute_target_seconds
        ),
        ObjectiveKind.TOTAL_COMMUTE: sum(
            variable * _required_duration(problem, student_index, location_index)
            for (student_index, location_index), variable in assignment_variables.items()
        ),
        ObjectiveKind.PREFERENCE_PENALTY: sum(preference_penalties),
        ObjectiveKind.ASSIGNMENT_CHANGES: sum(change_terms),
    }

    return (
        _BuiltModel(
            model=model,
            assignment_variables=assignment_variables,
            unassigned_variables=unassigned_variables,
            objective_expressions=objective_expressions,
            preferences=preferences,
            prior_assignments=prior_assignments,
        ),
        tuple(unavailable_students),
    )


def _validate(problem: OptimizationProblem) -> None:
    _validate_ids(problem)
    if not problem.locations and problem.students:
        raise OptimizationInputError("at least one placement location is required")
    if problem.config.time_limit_seconds <= 0:
        raise OptimizationInputError("time limit must be greater than zero")
    if problem.config.commute_target_seconds < 0:
        raise OptimizationInputError("commute target cannot be negative")
    if len(set(problem.config.objectives)) != len(problem.config.objectives):
        raise OptimizationInputError("objective priorities cannot contain duplicates")

    for location in problem.locations:
        if location.capacity < 0:
            raise OptimizationInputError(f"capacity cannot be negative: {location.id}")
        if location.minimum_capacity < 0:
            raise OptimizationInputError(f"minimum capacity cannot be negative: {location.id}")
        if location.minimum_capacity > location.capacity:
            raise OptimizationInputError(f"minimum capacity exceeds capacity: {location.id}")

    _validate_matrix(problem.durations_seconds, problem, "duration")
    if problem.distances_meters is not None:
        _validate_matrix(problem.distances_meters, problem, "distance")

    rules = problem.rules
    student_ids = {student.id for student in problem.students}
    location_ids = {location.id for location in problem.locations}
    _validate_preferences(rules.eligible_locations, "eligibility", student_ids, location_ids)
    _validate_preferences(rules.preferences, "preferences", student_ids, location_ids)
    _validate_pairs(
        rules.pinned,
        "pinned assignment",
        student_ids,
        location_ids,
        unique_students=True,
    )
    _validate_pairs(rules.prohibited, "prohibited assignment", student_ids, location_ids)
    _validate_pairs(
        rules.prior_assignments,
        "prior assignment",
        student_ids,
        location_ids,
        unique_students=True,
    )
    commute_limit_students = [student_id for student_id, _ in rules.student_commute_limits]
    if len(set(commute_limit_students)) != len(commute_limit_students):
        raise OptimizationInputError("student commute limits contain duplicates")
    for student_id, limit in rules.student_commute_limits:
        if student_id not in student_ids:
            raise OptimizationInputError(f"commute limit references unknown student: {student_id}")
        if limit < 0:
            raise OptimizationInputError("commute limits cannot be negative")
    if rules.maximum_commute_seconds is not None and rules.maximum_commute_seconds < 0:
        raise OptimizationInputError("maximum commute cannot be negative")
    for label, groups in (("together", rules.together), ("separate", rules.separate)):
        for group in groups:
            if len(group.student_ids) < 2:
                raise OptimizationInputError(f"{label} groups require at least two students")
            if len(set(group.student_ids)) != len(group.student_ids):
                raise OptimizationInputError(f"{label} group repeats a student")
            unknown = set(group.student_ids) - student_ids
            if unknown:
                raise OptimizationInputError(
                    f"{label} group references unknown student: {sorted(unknown)[0]}"
                )


def _validate_ids(problem: OptimizationProblem) -> None:
    student_ids = [student.id.strip() for student in problem.students]
    location_ids = [location.id.strip() for location in problem.locations]
    if any(not value for value in student_ids):
        raise OptimizationInputError("every student must have a non-empty id")
    if any(not value for value in location_ids):
        raise OptimizationInputError("every location must have a non-empty id")
    if len(set(student_ids)) != len(student_ids):
        raise OptimizationInputError("student ids must be unique")
    if len(set(location_ids)) != len(location_ids):
        raise OptimizationInputError("location ids must be unique")


def _validate_matrix(
    matrix: tuple[tuple[int | None, ...], ...],
    problem: OptimizationProblem,
    label: str,
) -> None:
    if len(matrix) != len(problem.students):
        raise OptimizationInputError(f"{label} matrix must contain one row per student")
    for row in matrix:
        if len(row) != len(problem.locations):
            raise OptimizationInputError(f"{label} matrix must contain one column per location")
        if any(value is not None and value < 0 for value in row):
            raise OptimizationInputError(f"{label} values cannot be negative")


def _validate_preferences(
    records: tuple[Preference, ...],
    label: str,
    student_ids: set[str],
    location_ids: set[str],
) -> None:
    seen_students: set[str] = set()
    for record in records:
        if record.student_id not in student_ids:
            raise OptimizationInputError(f"{label} references unknown student: {record.student_id}")
        if record.student_id in seen_students:
            raise OptimizationInputError(f"{label} repeats student: {record.student_id}")
        seen_students.add(record.student_id)
        if len(set(record.location_ids)) != len(record.location_ids):
            raise OptimizationInputError(f"{label} repeats a location for {record.student_id}")
        unknown = set(record.location_ids) - location_ids
        if unknown:
            raise OptimizationInputError(
                f"{label} references unknown location: {sorted(unknown)[0]}"
            )


def _validate_pairs(
    pairs,
    label: str,
    student_ids: set[str],
    location_ids: set[str],
    *,
    unique_students: bool = False,
) -> None:
    seen: set[tuple[str, str]] = set()
    seen_students: set[str] = set()
    for pair in pairs:
        if pair.student_id not in student_ids:
            raise OptimizationInputError(f"{label} references unknown student: {pair.student_id}")
        if pair.location_id not in location_ids:
            raise OptimizationInputError(f"{label} references unknown location: {pair.location_id}")
        key = (pair.student_id, pair.location_id)
        if key in seen:
            raise OptimizationInputError(
                f"duplicate {label}: {pair.student_id}, {pair.location_id}"
            )
        seen.add(key)
        if unique_students and pair.student_id in seen_students:
            raise OptimizationInputError(f"{label} repeats student: {pair.student_id}")
        seen_students.add(pair.student_id)


def _objective_order(config: OptimizationConfig) -> tuple[ObjectiveKind, ...]:
    objectives = config.objectives
    if config.allow_unassigned:
        objectives = tuple(
            objective for objective in objectives if objective is not ObjectiveKind.UNASSIGNED_COUNT
        )
        return (ObjectiveKind.UNASSIGNED_COUNT, *objectives)
    return tuple(
        objective for objective in objectives if objective is not ObjectiveKind.UNASSIGNED_COUNT
    )


def _configured_solver(remaining_seconds: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.01, remaining_seconds)
    # A single worker and stable model insertion order provide repeatable tie behavior.
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.log_search_progress = False
    return solver


def _result_from_solution(
    problem: OptimizationProblem,
    built: _BuiltModel,
    solver: cp_model.CpSolver,
    metrics: tuple[OptimizationMetric, ...],
    *,
    optimal: bool,
) -> OptimizationResult:
    placements: list[Placement] = []
    counts = [0] * len(problem.locations)
    durations: list[int] = []
    unassigned: list[str] = []

    for student_index, student in enumerate(problem.students):
        selected_location: int | None = None
        for location_index in range(len(problem.locations)):
            variable = built.assignment_variables.get((student_index, location_index))
            if variable is not None and solver.value(variable):
                selected_location = location_index
                break

        if selected_location is None:
            unassigned.append(student.id)
            placements.append(
                Placement(
                    student_id=student.id,
                    location_id=None,
                    duration_seconds=None,
                    distance_meters=None,
                    preference_rank=None,
                    changed_from_prior=student.id in built.prior_assignments,
                )
            )
            continue

        location = problem.locations[selected_location]
        duration = _required_duration(problem, student_index, selected_location)
        distance = (
            problem.distances_meters[student_index][selected_location]
            if problem.distances_meters is not None
            else None
        )
        choices = built.preferences.get(student.id, ())
        preference_rank = choices.index(location.id) + 1 if location.id in choices else None
        previous = built.prior_assignments.get(student.id)
        placements.append(
            Placement(
                student_id=student.id,
                location_id=location.id,
                duration_seconds=duration,
                distance_meters=distance,
                preference_rank=preference_rank,
                changed_from_prior=previous is not None and previous != location.id,
            )
        )
        counts[selected_location] += 1
        durations.append(duration)

    proof = SolveProof.OPTIMAL if optimal else SolveProof.FEASIBLE
    message = (
        "The configured priorities were optimized and proven."
        if optimal
        else (
            "A usable assignment was found, but not every priority was proven within "
            "the time limit."
        )
    )
    if unassigned:
        message += f" {len(unassigned)} student(s) remain unassigned."
    return OptimizationResult(
        proof=proof,
        placements=tuple(placements),
        metrics=metrics,
        total_commute_seconds=sum(durations),
        maximum_commute_seconds=max(durations, default=0),
        average_commute_seconds=(sum(durations) / len(durations) if durations else 0.0),
        unassigned_student_ids=tuple(unassigned),
        location_counts=tuple(
            (location.id, counts[index]) for index, location in enumerate(problem.locations)
        ),
        message=message,
    )


def _empty_result(problem: OptimizationProblem) -> OptimizationResult:
    return OptimizationResult(
        proof=SolveProof.OPTIMAL,
        placements=(),
        metrics=(),
        total_commute_seconds=0,
        maximum_commute_seconds=0,
        average_commute_seconds=0.0,
        unassigned_student_ids=(),
        location_counts=tuple((location.id, 0) for location in problem.locations),
        message="There are no students to assign.",
    )


def _infeasible_result(problem: OptimizationProblem, message: str) -> OptimizationResult:
    return OptimizationResult(
        proof=SolveProof.INFEASIBLE,
        placements=(),
        metrics=(),
        total_commute_seconds=0,
        maximum_commute_seconds=0,
        average_commute_seconds=0.0,
        unassigned_student_ids=(),
        location_counts=tuple((location.id, 0) for location in problem.locations),
        message=message,
    )


def _preference_map(records: tuple[Preference, ...]) -> dict[str, tuple[str, ...]]:
    return {record.student_id: record.location_ids for record in records}


def _required_duration(
    problem: OptimizationProblem,
    student_index: int,
    location_index: int,
) -> int:
    duration = problem.durations_seconds[student_index][location_index]
    if duration is None:
        raise RuntimeError("an assignment variable references an unavailable route")
    return duration


def _expression_value(
    solver: cp_model.CpSolver,
    expression: cp_model.LinearExpr | int,
) -> int:
    return int(expression) if isinstance(expression, int) else int(solver.value(expression))
