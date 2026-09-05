"""Seeded combined-rule oracle check; no application files or network touched."""

import random
from itertools import product

from placement_optimizer.domain import Location, Student
from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    ObjectiveKind,
    OptimizationConfig,
    OptimizationProblem,
    Preference,
    SolveProof,
    StudentLocationPair,
    solve_optimization_problem,
)

r = random.Random(20260905)


def check_case(case):
    n = r.randint(1, 5)
    m = r.randint(1, 3)
    students = tuple(Student(f"s{i}", f"Student {i}") for i in range(n))
    caps = [r.randint(0, n) for _ in range(m)]
    mins = [r.randint(0, c) if r.random() < 0.25 else 0 for c in caps]
    locations = tuple(
        Location(f"l{j}", f"Location {j}", caps[j], minimum_capacity=mins[j]) for j in range(m)
    )
    times = tuple(
        tuple(None if r.random() < 0.15 else r.randint(0, 30) for j in range(m)) for i in range(n)
    )
    eligible = {i: tuple(r.sample(range(m), r.randint(0, m))) for i in range(n) if r.random() < 0.3}
    choices = {i: tuple(r.sample(range(m), r.randint(1, m))) for i in range(n) if r.random() < 0.6}
    pins = {i: r.randrange(m) for i in range(n) if r.random() < 0.15}
    forbids = {(i, j) for i in range(n) for j in range(m) if r.random() < 0.1}
    prior = {i: r.randrange(m) for i in range(n) if r.random() < 0.4}
    together = [tuple(r.sample(range(n), 2))] if n >= 2 and r.random() < 0.3 else []
    apart = [tuple(r.sample(range(n), 2))] if n >= 2 and r.random() < 0.3 else []
    maximum = r.choice([None, 15, 25])
    limits = {i: r.randint(5, 30) for i in range(n) if r.random() < 0.25}
    unassigned = r.choice([True, False])
    target = 15
    goals = list(ObjectiveKind)
    goals.remove(ObjectiveKind.UNASSIGNED_COUNT)
    r.shuffle(goals)
    rules = AssignmentRules(
        eligible_locations=tuple(
            Preference(f"s{i}", tuple(f"l{j}" for j in js)) for i, js in eligible.items()
        ),
        preferences=tuple(
            Preference(f"s{i}", tuple(f"l{j}" for j in js)) for i, js in choices.items()
        ),
        pinned=tuple(StudentLocationPair(f"s{i}", f"l{j}") for i, j in pins.items()),
        prohibited=tuple(StudentLocationPair(f"s{i}", f"l{j}") for i, j in sorted(forbids)),
        prior_assignments=tuple(StudentLocationPair(f"s{i}", f"l{j}") for i, j in prior.items()),
        together=tuple(GroupRule(tuple(f"s{i}" for i in g)) for g in together),
        separate=tuple(GroupRule(tuple(f"s{i}" for i in g)) for g in apart),
        maximum_commute_seconds=maximum,
        student_commute_limits=tuple((f"s{i}", v) for i, v in limits.items()),
    )
    p = OptimizationProblem(
        students,
        locations,
        times,
        rules=rules,
        config=OptimizationConfig(
            objectives=tuple(goals), allow_unassigned=unassigned, commute_target_seconds=target
        ),
    )

    def allowed(a):
        if any(not mins[j] <= a.count(j) <= caps[j] for j in range(m)):
            return False
        for i, j in enumerate(a):
            if i in pins and pins[i] != j:
                return False
            if j < 0:
                continue
            if times[i][j] is None or (i, j) in forbids:
                return False
            if i in eligible and j not in eligible[i]:
                return False
            limit = limits.get(i, maximum)
            if limit is not None and times[i][j] > limit:
                return False
        if any(len({a[i] for i in g}) != 1 for g in together):
            return False
        return not any(
            len([a[i] for i in g if a[i] >= 0]) != len({a[i] for i in g if a[i] >= 0})
            for g in apart
        )

    def score(a):
        drives = [times[i][j] for i, j in enumerate(a) if j >= 0]
        values = {
            ObjectiveKind.MAXIMUM_COMMUTE: max(drives, default=0),
            ObjectiveKind.TOTAL_COMMUTE: sum(drives),
            ObjectiveKind.OVER_TARGET_COUNT: sum(v > target for v in drives),
            ObjectiveKind.PREFERENCE_PENALTY: sum(
                choices[i].index(j) if j in choices[i] else len(choices[i])
                for i, j in enumerate(a)
                if j >= 0 and i in choices
            ),
            ObjectiveKind.ASSIGNMENT_CHANGES: sum(a[i] != j for i, j in prior.items()),
        }
        return ((a.count(-1),) if unassigned else ()) + tuple(values[g] for g in goals)

    feasible = [a for a in product(range(-1 if unassigned else 0, m), repeat=n) if allowed(a)]
    result = solve_optimization_problem(p)
    if not feasible:
        assert result.proof == SolveProof.INFEASIBLE, (case, result)
    else:
        assert result.proof == SolveProof.OPTIMAL, (case, result)
        a = tuple(
            -1 if q.location_id is None else int(q.location_id[1:]) for q in result.placements
        )
        assert allowed(a), (case, a)
        assert score(a) == min(map(score, feasible)), (case, a, score(a), min(map(score, feasible)))


for case in range(300):
    check_case(case)

print(
    "300 seeded combined-constraint/objective problems matched independent exhaustive enumeration."
)
