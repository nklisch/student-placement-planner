"""Outcome banners, conditional content, and results-table behavior."""

from __future__ import annotations

from PySide6.QtCore import Qt

from placement_optimizer.application import OutcomeKind, SolveProjectOutcome
from placement_optimizer.optimization import (
    ObjectiveKind,
    OptimizationMetric,
    OptimizationResult,
    Placement,
    SolveProof,
)
from placement_optimizer.ui.pages.results import format_drive
from placement_optimizer.ui.printing import (
    PrintLayout,
    PrintOptions,
    ResultsPrintPreviewDialog,
    build_results_print_html,
)

HORIZONTAL = Qt.Orientation.Horizontal


def _result(**overrides) -> OptimizationResult:
    base = {
        "proof": SolveProof.OPTIMAL,
        "placements": (
            Placement("s1", "l1", 300, None, 1, False),
            Placement("s2", None, None, None, None, False),
        ),
        "metrics": (OptimizationMetric(ObjectiveKind.OVER_TARGET_COUNT, 0),),
        "total_commute_seconds": 300,
        "maximum_commute_seconds": 300,
        "average_commute_seconds": 300.0,
        "unassigned_student_ids": (),
        "location_counts": (("l1", 1), ("l2", 0)),
        "message": "",
    }
    base.update(overrides)
    return OptimizationResult(**base)


def _show(window, outcome, project) -> None:
    window.pages[4].show_outcome(outcome, project)
    window.controller.notify()


def test_success_banner_and_capacity_text(ready_window) -> None:
    window = ready_window
    session = window.controller.session
    project = session.build_project().project
    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "",
        _result(
            placements=tuple(
                Placement(student.id, project.locations[0].id, 300, None, None, False)
                for student in project.students[:2]
            ),
            location_counts=((project.locations[0].id, 2),),
        ),
    )
    _show(window, outcome, project)

    results = window.pages[4]
    assert results.banner.title.text() == "Placements found — every rule is satisfied."
    assert results.export_button.isEnabled()
    assert results.print_button.isEnabled()


def test_unassigned_banner_and_students_sort_first(ready_window) -> None:
    window = ready_window
    project = window.controller.session.build_project().project
    first, second = project.students[:2]
    outcome = SolveProjectOutcome(
        OutcomeKind.NEEDS_ATTENTION,
        "Not enough spaces for everyone.",
        _result(
            placements=(
                Placement(first.id, project.locations[0].id, 300, None, None, False),
                Placement(second.id, None, None, None, None, False),
            ),
            unassigned_student_ids=(second.id,),
        ),
    )
    _show(window, outcome, project)

    results = window.pages[4]
    assert "couldn't be placed" in results.banner.title.text()
    model = results.student_table.model()
    assert model.index(0, 1).data() == "Not placed"
    assert second.name in model.index(0, 0).data()
    assert "Not placed" in results.warnings.text()


def test_infeasible_and_not_solved_banners(ready_window) -> None:
    window = ready_window
    project = window.controller.session.build_project().project

    _show(
        window,
        SolveProjectOutcome(OutcomeKind.INFEASIBLE, "No assignment satisfies all rules."),
        project,
    )
    assert window.pages[4].banner.title.text() == "No arrangement fits."
    assert not window.pages[4].recovery_actions.isHidden()

    _show(window, SolveProjectOutcome(OutcomeKind.NOT_SOLVED, ""), project)
    assert window.pages[4].banner.title.text() == "Not solved in time."


def test_drive_format_rounds_before_splitting_hours_and_minutes() -> None:
    assert format_drive(7_199) == "2 h"
    assert format_drive(5_430) == "1 h 30 min"


def test_choice_column_only_when_choices_exist(ready_window) -> None:
    window = ready_window
    session = window.controller.session
    project = session.build_project().project
    assert project.rules.preferences  # sample data has choices

    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "",
        _result(
            placements=tuple(
                Placement(student.id, project.locations[0].id, 300, None, 1, False)
                for student in project.students[:2]
            )
        ),
    )
    _show(window, outcome, project)
    headers = [
        window.pages[4].student_table.model().headerData(column, HORIZONTAL)
        for column in range(window.pages[4].student_table.model().columnCount())
    ]
    assert "Choice" in headers

    # Remove choices and rebuild: the column disappears.
    from dataclasses import replace

    session.set_rules(replace(session.rules, preferences=()))
    window.controller.notify()
    project = session.build_project().project
    _show(window, outcome, project)
    headers = [
        window.pages[4].student_table.model().headerData(column, HORIZONTAL)
        for column in range(window.pages[4].student_table.model().columnCount())
    ]
    assert "Choice" not in headers


def test_print_html_can_hide_driving_information(ready_window) -> None:
    project = ready_window.controller.session.build_project().project
    student = project.students[0]
    location = project.locations[0]
    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "Every rule is satisfied.",
        _result(placements=(Placement(student.id, location.id, 300, 1_250, None, False),)),
    )

    with_driving = build_results_print_html(outcome, project, PrintOptions())
    without_driving = build_results_print_html(
        outcome,
        project,
        PrintOptions(include_driving=False),
    )

    assert "Drive" in with_driving
    assert "Distance" in with_driving
    assert "5 min" in with_driving
    assert "Drive" not in without_driving
    assert "Distance" not in without_driving
    assert student.name in without_driving
    assert location.name in without_driving


def test_print_preview_exposes_layout_and_driving_options(ready_window, qtbot) -> None:
    project = ready_window.controller.session.build_project().project
    student = project.students[0]
    location = project.locations[0]
    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "",
        _result(placements=(Placement(student.id, location.id, 300, None, None, False),)),
    )
    dialog = ResultsPrintPreviewDialog(outcome, project, ready_window)
    qtbot.addWidget(dialog)

    assert dialog.print_options() == PrintOptions()
    dialog.layout_combo.setCurrentIndex(1)
    dialog.include_driving.setChecked(False)
    assert dialog.print_options() == PrintOptions(PrintLayout.BY_PLACEMENT, False)


def test_print_html_can_group_students_by_placement(ready_window) -> None:
    project = ready_window.controller.session.build_project().project
    first, second = project.students[:2]
    location = project.locations[0]
    outcome = SolveProjectOutcome(
        OutcomeKind.NEEDS_ATTENTION,
        "One student is not placed.",
        _result(
            placements=(
                Placement(first.id, location.id, 300, None, None, False),
                Placement(second.id, None, None, None, None, False),
            )
        ),
    )

    html = build_results_print_html(
        outcome,
        project,
        PrintOptions(layout=PrintLayout.BY_PLACEMENT, include_driving=False),
    )

    assert f"{location.name} <span class='muted'>— 1 of {location.capacity}</span>" in html
    assert "Not placed <span class='muted'>— 1</span>" in html
    assert html.index(location.name) < html.index("Not placed")
    assert first.name in html
    assert second.name in html


def test_road_distance_column_appears_when_provider_supplies_it(ready_window) -> None:
    window = ready_window
    project = window.controller.session.build_project().project
    student = project.students[0]
    location = project.locations[0]
    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "",
        _result(placements=(Placement(student.id, location.id, 300, 1_250, None, False),)),
    )

    _show(window, outcome, project)

    model = window.pages[4].student_table.model()
    headers = [model.headerData(column, HORIZONTAL) for column in range(model.columnCount())]
    assert "Distance" in headers
    distance_column = headers.index("Distance")
    assert model.index(0, distance_column).data() == "1.2 km"


def test_over_target_warning_strip(ready_window) -> None:
    window = ready_window
    project = window.controller.session.build_project().project
    outcome = SolveProjectOutcome(
        OutcomeKind.SUCCESS,
        "",
        _result(metrics=(OptimizationMetric(ObjectiveKind.OVER_TARGET_COUNT, 3),)),
    )
    _show(window, outcome, project)
    assert "3 students drive more than the 30-minute target." in window.pages[4].warnings.text()


def test_cancelled_outcome_keeps_previous_results(ready_window) -> None:
    window = ready_window
    project = window.controller.session.build_project().project
    _show(window, SolveProjectOutcome(OutcomeKind.CANCELLED, ""), project)
    results = window.pages[4]
    assert results.banner.title.text() == "Cancelled."
    assert not results.export_button.isEnabled()
