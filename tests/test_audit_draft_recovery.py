"""Regression coverage for editable identifiers, travel freshness, and project recovery."""

from placement_optimizer.application import DraftSession, LocationDraft, StudentDraft, TravelMode
from placement_optimizer.optimization import AssignmentRules, StudentLocationPair
from placement_optimizer.projects import load_draft_session, save_draft_session
from placement_optimizer.travel import TravelMatrix


def roster():
    session = DraftSession()
    session.add_student(
        StudentDraft("a", name="A", id="s1", address="Old address", coordinates="51.5, -0.12")
    )
    session.add_student(StudentDraft("b", name="B", id="s2"))
    session.add_location(LocationDraft("x", name="X", id="l1", capacity="2"))
    session.add_location(LocationDraft("y", name="Y", id="l2", capacity="2"))
    session.set_rules(
        AssignmentRules(pinned=(StudentLocationPair("s1", "l1"), StudentLocationPair("s2", "l2")))
    )
    return session


def test_duplicate_id_repair_preserves_rule_ownership_after_save(tmp_path):
    session = roster()
    session.update_student(0, id="s2")
    assert [p.student_id for p in session.rules.pinned] == ["s1", "s2"]
    path = tmp_path / "repair.spp"
    save_draft_session(session, path)
    session = load_draft_session(path)
    session.update_student(0, id="s3")
    assert session.rules.pinned == (
        StudentLocationPair("s3", "l1"),
        StudentLocationPair("s2", "l2"),
    )


def test_id_swaps_are_atomic_for_students_and_locations():
    session = roster()
    session.update_student(0, id="s2")
    session.update_student(1, id="s1")
    session.update_location(0, id="l2")
    session.update_location(1, id="l1")
    assert session.rules.pinned == (
        StudentLocationPair("s2", "l2"),
        StudentLocationPair("s1", "l1"),
    )


def test_deleting_new_duplicate_does_not_remove_original_students_rules():
    session = roster()
    session.add_student(StudentDraft("c", name="C", id="s1"))
    session.remove_students([2])
    assert session.rules.pinned == (
        StudentLocationPair("s1", "l1"),
        StudentLocationPair("s2", "l2"),
    )


def test_address_change_clears_coordinates_unless_explicitly_kept():
    session = roster()
    session.update_student(0, address="New address")
    assert session.students[0].coordinates == ""
    session.update_student(0, coordinates="52, 1")
    session.update_student(0, address="Override label", keep_coordinates=True)
    assert session.students[0].coordinates == "52, 1"


def test_metadata_edits_do_not_invalidate_road_times_and_undo_restores_validity():
    session = roster()
    session.set_travel_mode(TravelMode.COMMUNITY)
    matrix = TravelMatrix(((100, 200), (300, 400)), ((60, 120), (180, 240)), "community_osrm")
    session.set_calculated_matrix(matrix)
    session.update_student(0, name="Updated name")
    session.update_location(0, capacity="3")
    assert not session.calculated_travel_is_stale
    snapshot = session.grid_snapshot()
    session.set_manual_time("a", "x", "99")
    assert session.calculated_travel_is_stale
    session.restore_grid_snapshot(snapshot)
    assert not session.calculated_travel_is_stale
    assert session.calculated_matrix == matrix
    assert session.manual_times["a", "x"] == "1"
