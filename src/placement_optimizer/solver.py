"""Exact capacitated assignment solver.

This problem is a minimum-cost bipartite flow problem, so it does not need a
large mixed-integer programming runtime.  Successive shortest augmenting paths
find the exact minimum-total-distance assignment.  The fair objective first
binary-searches for the smallest feasible maximum journey and then minimizes
total distance under that bound.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from heapq import heappop, heappush
from math import inf

from placement_optimizer.domain import (
    Assignment,
    AssignmentProblem,
    AssignmentResult,
    LocationUtilization,
    Objective,
)


class ProblemValidationError(ValueError):
    """The assignment input is internally inconsistent."""


class InfeasibleAssignmentError(ValueError):
    """No assignment can place every student under the stated constraints."""

    def __init__(self, message: str, *, student_ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.student_ids = student_ids


@dataclass(slots=True)
class _Edge:
    to: int
    reverse_index: int
    capacity: int
    cost: int


class _FlowNetwork:
    def __init__(self, size: int) -> None:
        self.adjacency: list[list[_Edge]] = [[] for _ in range(size)]

    def add_edge(self, source: int, target: int, capacity: int, cost: int) -> _Edge:
        forward = _Edge(target, len(self.adjacency[target]), capacity, cost)
        reverse = _Edge(source, len(self.adjacency[source]), 0, -cost)
        self.adjacency[source].append(forward)
        self.adjacency[target].append(reverse)
        return forward

    def min_cost_flow(self, source: int, sink: int, requested_flow: int) -> tuple[int, int]:
        """Return (flow, cost) using non-negative initial forward-edge costs."""

        size = len(self.adjacency)
        potential = [0] * size
        flow = 0
        total_cost = 0

        while flow < requested_flow:
            distances = [inf] * size
            previous_node = [-1] * size
            previous_edge = [-1] * size
            distances[source] = 0
            queue: list[tuple[int, int]] = [(0, source)]

            while queue:
                distance, node = heappop(queue)
                if distance != distances[node]:
                    continue
                for edge_index, edge in enumerate(self.adjacency[node]):
                    if edge.capacity <= 0:
                        continue
                    reduced_cost = edge.cost + potential[node] - potential[edge.to]
                    candidate = distance + reduced_cost
                    if candidate < distances[edge.to]:
                        distances[edge.to] = candidate
                        previous_node[edge.to] = node
                        previous_edge[edge.to] = edge_index
                        heappush(queue, (candidate, edge.to))

            if distances[sink] == inf:
                break

            for node, distance in enumerate(distances):
                if distance != inf:
                    potential[node] += int(distance)

            increment = requested_flow - flow
            node = sink
            while node != source:
                parent = previous_node[node]
                if parent < 0:  # Defensive: sink was reachable, so this cannot normally occur.
                    increment = 0
                    break
                edge = self.adjacency[parent][previous_edge[node]]
                increment = min(increment, edge.capacity)
                node = parent

            if increment == 0:
                break

            path_cost = 0
            node = sink
            while node != source:
                parent = previous_node[node]
                edge = self.adjacency[parent][previous_edge[node]]
                path_cost += edge.cost
                edge.capacity -= increment
                reverse = self.adjacency[node][edge.reverse_index]
                reverse.capacity += increment
                node = parent

            flow += increment
            total_cost += increment * path_cost

        return flow, total_cost


class _CapacityNetwork:
    """Dinic max-flow network used by the minimax feasibility search."""

    def __init__(self, size: int) -> None:
        self.adjacency: list[list[list[int]]] = [[] for _ in range(size)]

    def add_edge(self, source: int, target: int, capacity: int) -> None:
        forward = [target, capacity, len(self.adjacency[target])]
        reverse = [source, 0, len(self.adjacency[source])]
        self.adjacency[source].append(forward)
        self.adjacency[target].append(reverse)

    def max_flow(self, source: int, sink: int, limit: int) -> int:
        total = 0
        size = len(self.adjacency)
        while total < limit:
            levels = [-1] * size
            levels[source] = 0
            queue = deque([source])
            while queue:
                node = queue.popleft()
                for target, capacity, _ in self.adjacency[node]:
                    if capacity and levels[target] < 0:
                        levels[target] = levels[node] + 1
                        queue.append(target)
            if levels[sink] < 0:
                break

            next_edges = [0] * size
            while total < limit:
                sent = self._send(source, sink, limit - total, levels, next_edges)
                if not sent:
                    break
                total += sent
        return total

    def _send(
        self,
        node: int,
        sink: int,
        amount: int,
        levels: list[int],
        next_edges: list[int],
    ) -> int:
        if node == sink:
            return amount
        while next_edges[node] < len(self.adjacency[node]):
            edge_index = next_edges[node]
            edge = self.adjacency[node][edge_index]
            target, capacity, reverse_index = edge
            if capacity and levels[target] == levels[node] + 1:
                sent = self._send(
                    target,
                    sink,
                    min(amount, capacity),
                    levels,
                    next_edges,
                )
                if sent:
                    edge[1] -= sent
                    self.adjacency[target][reverse_index][1] += sent
                    return sent
            next_edges[node] += 1
        return 0


def solve_assignment(
    problem: AssignmentProblem,
    objective: Objective = Objective.FAIR_DISTANCE,
) -> AssignmentResult:
    """Solve a placement problem exactly or raise a specific input/infeasibility error."""

    _validate_problem(problem)
    student_count = len(problem.students)

    if student_count == 0:
        return AssignmentResult(
            objective=objective,
            assignments=(),
            total_distance_meters=0,
            maximum_distance_meters=0,
            average_distance_meters=0.0,
            location_utilization=tuple(
                LocationUtilization(location.id, 0, location.capacity)
                for location in problem.locations
            ),
        )

    maximum_allowed: int | None = None
    if objective is Objective.FAIR_DISTANCE:
        maximum_allowed = _minimum_feasible_maximum(problem)
    elif objective is not Objective.TOTAL_DISTANCE:
        raise ProblemValidationError(f"unsupported objective: {objective}")

    location_indexes = _minimum_cost_assignment(problem, maximum_allowed)
    assignments = tuple(
        Assignment(
            student_id=student.id,
            location_id=problem.locations[location_index].id,
            distance_meters=_required_distance(problem, student_index, location_index),
            duration_seconds=(
                problem.durations_seconds[student_index][location_index]
                if problem.durations_seconds is not None
                else None
            ),
        )
        for student_index, (student, location_index) in enumerate(
            zip(problem.students, location_indexes, strict=True)
        )
    )

    total_distance = sum(assignment.distance_meters for assignment in assignments)
    counts = [0] * len(problem.locations)
    for location_index in location_indexes:
        counts[location_index] += 1

    return AssignmentResult(
        objective=objective,
        assignments=assignments,
        total_distance_meters=total_distance,
        maximum_distance_meters=max(a.distance_meters for a in assignments),
        average_distance_meters=total_distance / student_count,
        location_utilization=tuple(
            LocationUtilization(location.id, counts[index], location.capacity)
            for index, location in enumerate(problem.locations)
        ),
    )


def _validate_problem(problem: AssignmentProblem) -> None:
    student_ids = [student.id.strip() for student in problem.students]
    location_ids = [location.id.strip() for location in problem.locations]
    if any(not student_id for student_id in student_ids):
        raise ProblemValidationError("every student must have a non-empty id")
    if any(not location_id for location_id in location_ids):
        raise ProblemValidationError("every location must have a non-empty id")
    if len(set(student_ids)) != len(student_ids):
        raise ProblemValidationError("student ids must be unique")
    if len(set(location_ids)) != len(location_ids):
        raise ProblemValidationError("location ids must be unique")
    if any(location.capacity < 0 for location in problem.locations):
        raise ProblemValidationError("location capacity cannot be negative")
    if any(location.minimum_capacity for location in problem.locations):
        raise ProblemValidationError(
            "the independent reference solver does not support minimum location capacities"
        )
    if problem.students and not problem.locations:
        raise InfeasibleAssignmentError("at least one placement location is required")
    if sum(location.capacity for location in problem.locations) < len(problem.students):
        raise InfeasibleAssignmentError(
            "total location capacity is smaller than the number of students"
        )

    _validate_matrix(problem.distances_meters, problem, "distance")
    if problem.durations_seconds is not None:
        _validate_matrix(problem.durations_seconds, problem, "duration")

    unroutable = tuple(
        student.id
        for student, row in zip(problem.students, problem.distances_meters, strict=True)
        if all(distance is None for distance in row)
    )
    if unroutable:
        raise InfeasibleAssignmentError(
            "one or more students have no road route to any location",
            student_ids=unroutable,
        )


def _validate_matrix(
    matrix: tuple[tuple[int | None, ...], ...],
    problem: AssignmentProblem,
    label: str,
) -> None:
    if len(matrix) != len(problem.students):
        raise ProblemValidationError(f"{label} matrix must contain one row per student")
    for row in matrix:
        if len(row) != len(problem.locations):
            raise ProblemValidationError(f"{label} matrix must contain one column per location")
        if any(value is not None and value < 0 for value in row):
            raise ProblemValidationError(f"{label} values cannot be negative")


def _minimum_feasible_maximum(problem: AssignmentProblem) -> int:
    candidates = sorted(
        {distance for row in problem.distances_meters for distance in row if distance is not None}
    )
    low = 0
    high = len(candidates) - 1
    best: int | None = None
    while low <= high:
        middle = (low + high) // 2
        threshold = candidates[middle]
        if _is_feasible(problem, threshold):
            best = threshold
            high = middle - 1
        else:
            low = middle + 1
    if best is None:
        raise InfeasibleAssignmentError(
            "location capacities and available road routes cannot accommodate every student"
        )
    return best


def _is_feasible(problem: AssignmentProblem, maximum_distance: int) -> bool:
    student_count = len(problem.students)
    location_count = len(problem.locations)
    source = 0
    student_offset = 1
    location_offset = student_offset + student_count
    sink = location_offset + location_count
    network = _CapacityNetwork(sink + 1)

    for student_index, row in enumerate(problem.distances_meters):
        network.add_edge(source, student_offset + student_index, 1)
        for location_index, distance in enumerate(row):
            if distance is not None and distance <= maximum_distance:
                network.add_edge(
                    student_offset + student_index,
                    location_offset + location_index,
                    1,
                )
    for location_index, location in enumerate(problem.locations):
        network.add_edge(location_offset + location_index, sink, location.capacity)

    return network.max_flow(source, sink, student_count) == student_count


def _minimum_cost_assignment(
    problem: AssignmentProblem,
    maximum_distance: int | None,
) -> tuple[int, ...]:
    student_count = len(problem.students)
    location_count = len(problem.locations)
    source = 0
    student_offset = 1
    location_offset = student_offset + student_count
    sink = location_offset + location_count
    network = _FlowNetwork(sink + 1)
    assignment_edges: list[list[tuple[int, _Edge]]] = [[] for _ in problem.students]

    for student_index, row in enumerate(problem.distances_meters):
        network.add_edge(source, student_offset + student_index, 1, 0)
        for location_index, distance in enumerate(row):
            if distance is None or (maximum_distance is not None and distance > maximum_distance):
                continue
            edge = network.add_edge(
                student_offset + student_index,
                location_offset + location_index,
                1,
                distance,
            )
            assignment_edges[student_index].append((location_index, edge))
    for location_index, location in enumerate(problem.locations):
        network.add_edge(location_offset + location_index, sink, location.capacity, 0)

    flow, _ = network.min_cost_flow(source, sink, student_count)
    if flow != student_count:
        raise InfeasibleAssignmentError(
            "location capacities and available road routes cannot accommodate every student"
        )

    selected: list[int] = []
    for edges in assignment_edges:
        used_locations = [location_index for location_index, edge in edges if edge.capacity == 0]
        if len(used_locations) != 1:
            raise RuntimeError("solver produced an invalid assignment")
        selected.append(used_locations[0])
    return tuple(selected)


def _required_distance(
    problem: AssignmentProblem,
    student_index: int,
    location_index: int,
) -> int:
    distance = problem.distances_meters[student_index][location_index]
    if distance is None:  # The solver never creates an edge for an unavailable route.
        raise RuntimeError("solver selected an unavailable route")
    return distance
