"""One chronological data history avoids restoring unrelated later work."""

from placement_optimizer.ui.tablemodels import (
    LocationsTableModel,
    ManualTimesModel,
    StudentsTableModel,
)


def test_global_undo_reverses_latest_edit_across_pages(controller):
    students = StudentsTableModel(controller)
    locations = LocationsTableModel(controller)
    students.paste_block(0, 0, "Alice")
    locations.paste_block(0, 0, "Site\tl1\t5")
    assert students.undo is locations.undo is controller.undo
    # Undo from Students reverses the latest operation (Locations), not an old snapshot.
    students.undo.undo()
    assert len(controller.session.students) == 1
    assert controller.session.locations == []
    students.undo.undo()
    assert controller.session.students == []
    locations.undo.redo()
    locations.undo.redo()
    assert controller.session.locations[0].capacity == "5"


def test_bound_undo_cannot_reverse_an_intervening_edit(controller):
    students = StudentsTableModel(controller)
    students.paste_block(0, 0, "Alice")
    students.delete_rows([0])
    undo_removal = students.undo.bound_undo()
    students.paste_block(0, 0, "Bob")
    assert not undo_removal()
    assert [row.name for row in controller.session.students] == ["Bob"]


def test_manual_paste_keeps_valid_cells_and_reports_overflow(controller, fill_small):
    fill_small(controller)
    model = ManualTimesModel(controller)
    notices = []
    controller.notice.connect(notices.append)
    model.paste_block(0, 0, "5\t6\t7\n8\t9\t10\n11\t12\t13")
    assert model.data(model.index(0, 1)) == "6"
    assert model.data(model.index(1, 1)) == "9"
    assert notices and "5 extra cells" in notices[0]


def test_address_editor_can_keep_or_clear_existing_coordinates(controller):
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1\tOld street\t51, -1")
    controller.address_change_decision = lambda _name: "coordinates"
    model.setData(model.index(0, 2), "New street")
    assert controller.session.students[0].coordinates == "51, -1"
    controller.address_change_decision = lambda _name: "address"
    model.setData(model.index(0, 2), "Another street")
    assert controller.session.students[0].coordinates == ""
    model.undo.undo()
    # Repeated edits coalesce, restoring the original full row including its coordinates.
    assert controller.session.students[0].coordinates == "51, -1"


def test_address_repair_links_focus_the_real_roster_cell(ready_window):
    window = ready_window
    student = window.controller.session.active_students[0]
    window.navigate(3)
    window.pages[3].addressRepairRequested.emit("Student", student.id)
    assert window.stack.currentIndex() == 0
    index = window.pages[0].table.currentIndex()
    assert index.row() == 0
    assert window.pages[0].model.FIELDS[index.column()] == "address"


def test_invalid_distance_does_not_turn_seconds_into_minutes(window, fill_small):
    from placement_optimizer.projects import parse_matrix_csv

    fill_small(window.controller)
    page = window.pages[3]
    page._import_session = window.controller.session
    page._apply_import(
        parse_matrix_csv("student_id,location_id,duration_seconds,distance_km\ns1,l1,600,far\n")
    )
    raw = window.controller.session.manual_times["student-a", "location-a"]
    assert raw.startswith("10 [invalid CSV row:")
    assert "duration_seconds=600" in page.import_report.text()
    assert not window.controller.session.readiness().ready
