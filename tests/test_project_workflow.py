from __future__ import annotations

import json
from dataclasses import replace

import pytest

from placement_optimizer.application import OutcomeKind, PlacementProject, solve_project
from placement_optimizer.optimization import (
    AssignmentRules,
    ObjectiveKind,
    OptimizationCancellation,
    OptimizationConfig,
    Preference,
)
from placement_optimizer.projects import (
    IssueLevel,
    ProjectFileError,
    export_result_csv,
    load_project,
    parse_locations_csv,
    parse_matrix_csv,
    parse_students_csv,
    save_project,
)
from placement_optimizer.travel import matrix_from_entries


def test_csv_import_keeps_valid_rows_and_reports_bad_rows() -> None:
    imported = parse_students_csv(
        "\ufeffstudent_id;name;address;latitude;longitude\n"
        "s1;Alice;1 Main Street;;\n"
        "s2;Bob;;not-a-number;-1.2\n"
        "s3;Charlie;3 Main Street;51.5;-0.12\n"
    )

    assert [student.id for student in imported.items] == ["s1", "s3"]
    assert imported.error_count == 1
    assert imported.issues[0].row == 3
    assert len(imported.draft_rows) == 3
    assert imported.draft_rows[1].as_dict()["student_id"] == "s2"


def test_unrecognized_student_columns_are_reported() -> None:
    imported = parse_students_csv("unrelated,columns\nfoo,bar\n")
    assert imported.items == ()
    assert imported.error_count == 1
    assert "recognized" in imported.issues[0].message


def test_blank_location_capacity_remains_editable_and_unresolved() -> None:
    imported = parse_locations_csv("id,name,address,capacity\nl1,Library,1 High Street,\n")

    assert imported.items == ()
    assert imported.issues[0].level is IssueLevel.ERROR
    assert "required" in imported.issues[0].message
    assert imported.draft_rows[0].as_dict()["name"] == "Library"


def test_displayed_csv_headers_preserve_minimum_and_coordinates() -> None:
    batch = parse_locations_csv(
        'Name,ID,Capacity,Minimum,Address,Coordinates\nLibrary,L001,3,1,Main Street,"51.5, -0.12"\n'
    )
    assert not batch.issues
    assert batch.items[0].minimum_capacity == 1
    assert batch.items[0].coordinate.latitude == 51.5


@pytest.mark.parametrize("coordinate", ["not a point", "91, 0", "51.5,"])
def test_invalid_combined_coordinates_retain_original(coordinate) -> None:
    batch = parse_students_csv(f'Name,Coordinates\nAlice,"{coordinate}"\n')
    assert batch.error_count == 1
    assert batch.draft_rows[0].as_dict()["coordinates"] == coordinate


def test_populated_unknown_columns_warn_and_retain_values() -> None:
    batch = parse_locations_csv("Name,Capacity,Constraint,Empty\nLibrary,3,keep together,\n")
    assert batch.error_count == 0
    assert len(batch.issues) == 1
    assert batch.issues[0].level is IssueLevel.WARNING
    assert batch.draft_rows[0].as_dict()["constraint"] == "keep together"


def test_matrix_import_accepts_explicit_no_route() -> None:
    imported = parse_matrix_csv(
        "student_id,location_id,driving_minutes,distance_km\n"
        "s1,l1,12.5,7.2\n"
        "s1,l2,no route,no route\n"
    )

    assert imported.error_count == 0
    assert imported.items[0].duration_seconds == 750
    assert imported.items[0].distance_meters == 7200
    assert imported.items[1].duration_seconds is None


def test_manual_input_to_solve_and_export_vertical_slice() -> None:
    students = parse_students_csv("id,name\ns1,Alice\ns2,Bob\n").items
    locations = parse_locations_csv("id,name,capacity\nl1,Library,1\nl2,Workshop,1\n").items
    matrix_entries = parse_matrix_csv(
        "student_id,location_id,driving_minutes,distance_km\n"
        "s1,l1,5,3\n"
        "s1,l2,10,7\n"
        "s2,l1,8,5\n"
        "s2,l2,20,14\n"
    ).items
    travel = matrix_from_entries(students, locations, matrix_entries)
    project = PlacementProject(
        name="Example",
        students=students,
        locations=locations,
        travel_matrix=travel,
        rules=AssignmentRules(
            preferences=(
                Preference("s1", ("l1", "l2")),
                Preference("s2", ("l1", "l2")),
            )
        ),
        optimization=OptimizationConfig(
            objectives=(ObjectiveKind.MAXIMUM_COMMUTE, ObjectiveKind.TOTAL_COMMUTE)
        ),
    )

    outcome = solve_project(project)

    assert outcome.kind is OutcomeKind.SUCCESS
    assert outcome.result is not None
    assert outcome.result.maximum_commute_seconds == 600
    exported = export_result_csv(outcome.result, students, locations)
    assert "student_name" in exported
    assert "Alice" in exported
    assert "Workshop" in exported


def test_pre_cancelled_solve_returns_cancelled_outcome() -> None:
    cancellation = OptimizationCancellation()
    cancellation.cancel()

    outcome = solve_project(PlacementProject(), cancellation)

    assert outcome.kind is OutcomeKind.CANCELLED


def test_non_finite_matrix_value_becomes_an_import_issue() -> None:
    imported = parse_matrix_csv("student_id,location_id,driving_minutes\ns1,l1,Infinity\n")
    assert imported.items == ()
    assert imported.error_count == 1
    assert imported.draft_rows[0].as_dict()["driving_minutes"] == "Infinity"


def test_project_file_round_trip(tmp_path) -> None:
    students = parse_students_csv("id,name,address\ns1,Alice,1 Main Street\n").items
    locations = parse_locations_csv("id,name,capacity\nl1,Library,2\n").items
    entries = parse_matrix_csv(
        "student_id,location_id,driving_minutes,distance_km\ns1,l1,5,3\n"
    ).items
    original = PlacementProject(
        name="Saved example",
        students=students,
        locations=locations,
        travel_matrix=matrix_from_entries(students, locations, entries),
        rules=AssignmentRules(preferences=(Preference("s1", ("l1",)),)),
    )
    path = tmp_path / "example.spp"

    save_project(original, path)
    loaded = load_project(path)

    assert loaded == original
    assert solve_project(loaded).kind is OutcomeKind.SUCCESS


def test_project_missing_optional_settings_uses_documented_defaults(tmp_path) -> None:
    path = tmp_path / "minimal.spp"
    path.write_text(
        json.dumps({"schema_version": 1, "students": [], "locations": []}),
        encoding="utf-8",
    )
    loaded = load_project(path)
    assert loaded.optimization == OptimizationConfig()


@pytest.mark.parametrize(
    "bad_value",
    [
        {"optimization": {"allow_unassigned": "false"}},
        {"locations": [{"id": "l1", "name": "One", "capacity": 1.5}]},
        {"rules": {"student_commute_limits": [["s1"]]}},
    ],
)
def test_malformed_constraint_values_are_rejected(tmp_path, bad_value: dict) -> None:
    path = tmp_path / "malformed.spp"
    path.write_text(
        json.dumps({"schema_version": 1, "students": [], "locations": [], **bad_value}),
        encoding="utf-8",
    )
    with pytest.raises(ProjectFileError, match="could not be read"):
        load_project(path)


def test_project_save_replaces_existing_file(tmp_path) -> None:
    path = tmp_path / "example.spp"
    project = PlacementProject(name="First")
    save_project(project, path)
    save_project(replace(project, name="Second"), path)
    assert load_project(path).name == "Second"


def test_project_save_wraps_parent_creation_failure(tmp_path) -> None:
    occupied_path = tmp_path / "not-a-directory"
    occupied_path.write_text("occupied", encoding="utf-8")
    with pytest.raises(ProjectFileError, match="Could not save project"):
        save_project(PlacementProject(), occupied_path / "project.spp")


def test_corrupt_project_file_has_a_recoverable_error(tmp_path) -> None:
    path = tmp_path / "broken.spp"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ProjectFileError, match="Start a new project"):
        load_project(path)


def test_missing_travel_data_is_needs_attention_not_an_exception() -> None:
    project = PlacementProject(
        students=parse_students_csv("id,name\ns1,Alice\n").items,
        locations=parse_locations_csv("id,name,capacity\nl1,Library,1\n").items,
    )
    outcome = solve_project(project)
    assert outcome.kind is OutcomeKind.NEEDS_ATTENTION
    assert "driving times" in outcome.message
