from __future__ import annotations

from placement_optimizer.application import (
    DraftArea,
    DraftSession,
    LocationDraft,
    StudentDraft,
    TravelMode,
)
from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    Preference,
    StudentLocationPair,
)
from placement_optimizer.projects import (
    load_draft_session,
    save_draft_session,
    save_project,
)
from placement_optimizer.travel import TravelMatrix


def ready_session() -> DraftSession:
    session = DraftSession("Example")
    student_one = session.add_student(StudentDraft("student-a", "Alice", "s1", "1 Main Street"))
    student_two = session.add_student(StudentDraft("student-b", "Bob", "s2"))
    location_one = session.add_location(LocationDraft("location-a", "Library", "l1", "1"))
    location_two = session.add_location(LocationDraft("location-b", "Workshop", "l2", "1"))
    session.set_manual_time(student_one.key, location_one.key, "5")
    session.set_manual_time(student_one.key, location_two.key, "10")
    session.set_manual_time(student_two.key, location_one.key, "8")
    session.set_manual_time(student_two.key, location_two.key, "x")
    return session


def test_blank_session_reports_each_missing_step_without_crashing() -> None:
    readiness = DraftSession().readiness()
    assert readiness.ready is False
    assert readiness.students_ready is False
    assert readiness.locations_ready is False
    assert readiness.travel_ready is False


def test_manual_grid_builds_a_project_with_explicit_no_route() -> None:
    built = ready_session().build_project()
    assert built.readiness.ready is True
    assert built.project is not None
    assert built.project.travel_matrix is not None
    assert built.project.travel_matrix.durations_seconds == (
        (300, 600),
        (480, None),
    )
    assert built.project.travel_matrix.distances_meters == (
        (None, None),
        (None, None),
    )


def test_manual_distances_are_retained_when_supplied() -> None:
    session = ready_session()
    session.set_manual_distance("student-a", "location-a", 3200)
    built = session.build_project()
    assert built.project is not None
    assert built.project.travel_matrix is not None
    assert built.project.travel_matrix.distances_meters[0][0] == 3200


def test_public_grid_snapshot_restores_rows_times_and_distances() -> None:
    session = ready_session()
    session.set_manual_distance("student-a", "location-a", 3200)
    snapshot = session.grid_snapshot()
    session.remove_students([0])
    session.restore_grid_snapshot(snapshot)
    assert len(session.students) == 2
    assert session.manual_times["student-a", "location-a"] == "5"
    assert session.manual_distances_meters["student-a", "location-a"] == 3200


def test_id_only_extra_rows_are_ignored_but_partial_rows_block() -> None:
    session = ready_session()
    session.mark_result()
    model_version = session.model_version
    travel_version = session.travel_input_version
    ignored_student = session.add_student()
    ignored_location = session.add_location()

    built = session.build_project()

    assert built.readiness.ready
    assert built.project is not None
    assert len(built.project.students) == 2
    assert len(built.project.locations) == 2
    assert ignored_student not in session.active_students
    assert ignored_location not in session.active_locations
    assert session.model_version == model_version
    assert session.travel_input_version == travel_version
    assert not session.results_are_stale

    session.update_student(2, id="custom-student")
    session.update_location(2, id="custom-location")
    assert not session.readiness().ready

    session.update_student(2, id=ignored_student.id, address="3 Partial Street")
    session.update_location(2, id=ignored_location.id, capacity="1")
    readiness = session.readiness()

    assert not readiness.ready
    assert any(
        issue.row_key == ignored_student.key and issue.field == "name"
        for issue in readiness.issues
    )
    assert any(
        issue.row_key == ignored_location.key and issue.field == "name"
        for issue in readiness.issues
    )

    session.update_student(2, address="")
    session.update_location(2, capacity="")
    assert ignored_student.key in {row.key for row in session.active_students}
    assert ignored_location.key in {row.key for row in session.active_locations}
    assert not session.readiness().ready


def test_invalid_rows_and_cells_remain_in_draft_state() -> None:
    session = ready_session()
    session.update_location(0, capacity="")
    session.set_manual_time("student-a", "location-b", "many")

    built = session.build_project()

    assert built.project is None
    assert session.locations[0].capacity == ""
    assert session.manual_times["student-a", "location-b"] == "many"
    assert {issue.area for issue in built.readiness.issues} >= {
        DraftArea.LOCATIONS,
        DraftArea.TRAVEL,
    }


def test_new_location_preserves_existing_manual_times_and_adds_only_new_cells() -> None:
    session = ready_session()
    session.add_location(LocationDraft("location-c", "Clinic", "l3", "2"))
    readiness = session.readiness()
    assert readiness.missing_travel_cells == 2
    assert session.manual_times["student-a", "location-a"] == "5"


def test_calculated_travel_becomes_stale_after_roster_change() -> None:
    session = ready_session()
    session.set_travel_mode(TravelMode.GOOGLE)
    session.set_calculated_matrix(
        TravelMatrix(
            distances_meters=((100, 200), (300, 400)),
            durations_seconds=((10, 20), (30, 40)),
            source="google_routes",
        )
    )
    assert session.calculated_travel_is_stale is False

    session.update_student(0, address="2 Changed Street")

    assert session.calculated_travel_is_stale is True
    assert session.build_project().readiness.travel_ready is False


def test_result_staleness_ignores_project_name_but_tracks_model_changes() -> None:
    session = ready_session()
    session.mark_result()
    session.set_name("Renamed")
    assert session.results_are_stale is False
    session.set_manual_time("student-a", "location-a", "6")
    assert session.results_are_stale is True


def test_renaming_ids_updates_rules() -> None:
    session = ready_session()
    session.set_rules(
        AssignmentRules(
            preferences=(Preference("s1", ("l1", "l2")),),
            pinned=(StudentLocationPair("s1", "l1"),),
            together=(GroupRule(("s1", "s2")),),
        )
    )

    session.update_student(0, id="student-one")
    session.update_location(0, id="library")

    assert session.rules.preferences[0] == Preference("student-one", ("library", "l2"))
    assert session.rules.pinned[0] == StudentLocationPair("student-one", "library")
    assert session.rules.together[0] == GroupRule(("student-one", "s2"))


def test_deleting_referenced_rows_cleans_rules_and_keeps_session_usable() -> None:
    session = ready_session()
    session.set_rules(
        AssignmentRules(
            preferences=(Preference("s1", ("l1", "l2")),),
            pinned=(StudentLocationPair("s1", "l1"),),
            together=(GroupRule(("s1", "s2")),),
        )
    )

    session.remove_students([1])
    session.remove_locations([0])

    assert session.rules.together == ()
    assert session.rules.pinned == ()
    assert session.rules.preferences == (Preference("s1", ("l2",)),)


def test_saving_drops_ignored_extra_rows(tmp_path) -> None:
    session = ready_session()
    session.add_student()
    session.add_location()
    path = tmp_path / "without-extra-rows.spp"

    save_draft_session(session, path)
    restored = load_draft_session(path)

    assert len(restored.students) == 2
    assert len(restored.locations) == 2
    assert restored.build_project().readiness.ready


def test_incomplete_draft_file_round_trip_preserves_raw_rows_and_cells(tmp_path) -> None:
    session = ready_session()
    session.update_location(0, capacity="")
    session.set_manual_time("student-a", "location-b", "many")
    session.set_manual_distance("student-a", "location-a", 3200)
    path = tmp_path / "draft.spp"

    save_draft_session(session, path)
    restored = load_draft_session(path)

    assert restored.locations[0].capacity == ""
    assert restored.manual_times["student-a", "location-b"] == "many"
    assert restored.manual_distances_meters["student-a", "location-a"] == 3200
    assert restored.is_modified is False


def test_draft_loader_accepts_earlier_valid_project_files(tmp_path) -> None:
    session = ready_session()
    project = session.build_project().project
    assert project is not None
    path = tmp_path / "legacy.spp"
    save_project(project, path)
    restored = load_draft_session(path)
    assert restored.build_project().project == project


def test_calculated_matrix_must_match_selected_provider_mode() -> None:
    session = ready_session()
    matrix = session.build_project().project.travel_matrix
    session.set_travel_mode(TravelMode.GOOGLE)
    session.set_calculated_matrix(
        TravelMatrix(matrix.distances_meters, matrix.durations_seconds, "google_routes")
    )
    assert not session.calculated_travel_is_stale

    session.set_travel_mode(TravelMode.OFFLINE)
    assert session.calculated_travel_is_stale

    session.set_travel_mode(TravelMode.GOOGLE)
    assert not session.calculated_travel_is_stale

    session.set_travel_mode(TravelMode.COMMUNITY)
    assert session.calculated_travel_is_stale
    session.set_calculated_matrix(
        TravelMatrix(matrix.distances_meters, matrix.durations_seconds, "community_osrm")
    )
    assert not session.calculated_travel_is_stale

    session.set_travel_mode(TravelMode.OPENROUTESERVICE)
    assert session.calculated_travel_is_stale
    session.set_calculated_matrix(
        TravelMatrix(matrix.distances_meters, matrix.durations_seconds, "openrouteservice")
    )
    assert not session.calculated_travel_is_stale


def test_manual_override_marks_provider_matrix_stale_and_recalculation_clears_old_distance() -> (
    None
):
    session = ready_session()
    original = session.build_project().project.travel_matrix
    session.set_travel_mode(TravelMode.GOOGLE)
    session.set_calculated_matrix(
        TravelMatrix(
            ((1000, 2000), (3000, 4000)),
            original.durations_seconds,
            "google_routes",
        )
    )

    session.set_manual_time("student-a", "location-a", "6")
    assert session.calculated_travel_is_stale

    session.set_calculated_matrix(
        TravelMatrix(
            ((None, 2000), (3000, 4000)),
            original.durations_seconds,
            "google_routes",
        )
    )
    assert ("student-a", "location-a") not in session.manual_distances_meters


def test_stale_wrong_sized_provider_matrix_does_not_break_draft_reopen(tmp_path) -> None:
    session = ready_session()
    original = session.build_project().project.travel_matrix
    session.set_travel_mode(TravelMode.GOOGLE)
    session.set_calculated_matrix(
        TravelMatrix(original.distances_meters, original.durations_seconds, "google_routes")
    )
    session.add_student(StudentDraft("student-c", "Cara", "s3"))
    path = tmp_path / "stale-provider.spp"

    save_draft_session(session, path)
    restored = load_draft_session(path)

    assert len(restored.students) == 3
    assert restored.calculated_matrix is None
    assert restored.manual_times["student-a", "location-a"] == "5"


def test_project_round_trip_populates_editable_manual_grid() -> None:
    original = ready_session().build_project().project
    assert original is not None
    restored = DraftSession.from_project(original)
    assert restored.is_modified is False
    assert restored.manual_times["student-row-1", "location-row-1"] == "5"
    assert restored.build_project().project == original
