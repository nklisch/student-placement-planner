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


def test_incomplete_draft_file_round_trip_preserves_raw_rows_and_cells(tmp_path) -> None:
    session = ready_session()
    session.update_location(0, capacity="")
    session.set_manual_time("student-a", "location-b", "many")
    session.set_manual_distance("student-a", "location-a", 3200)
    path = tmp_path / "draft.spo.json"

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
    path = tmp_path / "legacy.spo.json"
    save_project(project, path)
    restored = load_draft_session(path)
    assert restored.build_project().project == project


def test_project_round_trip_populates_editable_manual_grid() -> None:
    original = ready_session().build_project().project
    assert original is not None
    restored = DraftSession.from_project(original)
    assert restored.is_modified is False
    assert restored.manual_times["student-row-1", "location-row-1"] == "5"
    assert restored.build_project().project == original
