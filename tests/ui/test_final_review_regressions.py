"""Parent-adjudicated regressions from the final integrated release review."""

import csv

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from placement_optimizer.application import (
    DraftSession,
    LocationDraft,
    StudentDraft,
    solve_project,
)
from placement_optimizer.optimization import AssignmentRules, StudentLocationPair
from placement_optimizer.projects import parse_locations_csv, parse_students_csv
from placement_optimizer.ui.pages.ruledialogs import CommuteLimitDialog


@pytest.mark.parametrize("area", ["student", "location"])
@pytest.mark.parametrize("remove", [True, False])
def test_ignored_rows_never_own_or_transfer_rule_references(area, remove):
    session = DraftSession()
    session.add_student(StudentDraft("a", name="Alice", id="S001"))
    session.add_location(LocationDraft("x", name="Site", id="L001", capacity="2"))
    session.set_rules(AssignmentRules(pinned=(StudentLocationPair("S001", "L001"),)))
    add = getattr(session, f"add_{area}")
    update = getattr(session, f"update_{area}")
    rows = getattr(session, f"{area}s")
    placeholder = add()
    assert placeholder.reference_id == ""
    update(0, id=placeholder.id)
    expected = session.rules.pinned
    if remove:
        getattr(session, f"remove_{area}s")([1])
    else:
        update(1, name="A different row")
        update(1, id="S003" if area == "student" else "L003")
        assert rows[0].reference_id != rows[1].reference_id
    assert session.rules.pinned == expected
    assert expected


def test_collapsing_student_limit_details_does_not_delete_rules(qtbot):
    dialog = CommuteLimitDialog([("s1", "Alice")], 2700, (("s1", 1200),))
    qtbot.addWidget(dialog)
    dialog.toggle.setChecked(False)
    dialog.accept()
    assert dialog.result_limits() == (2700, (("s1", 1200),))


def test_hidden_duplicate_student_limits_still_require_repair(qtbot, monkeypatch):
    dialog = CommuteLimitDialog([("s1", "Alice")], None, (("s1", 1200), ("s1", 2100)))
    qtbot.addWidget(dialog)
    dialog.toggle.setChecked(False)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog.accept()
    assert warnings
    assert dialog.result() == 0
    assert dialog.toggle.isChecked()


def test_modal_import_discard_serializes_other_completions(window):
    students, locations = window.pages[:2]
    session = window.controller.session
    students._import_session = session
    locations._import_session = session

    def finish_other_import():
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        try:
            locations._apply_import(parse_locations_csv("Name,Capacity\nKeep this site,3\n"))
            # The worker can finish while its apply is queued. Capture its session
            # rather than reading the cleared worker state when the queue drains.
            locations._import_session = None
            assert not session.locations
        finally:
            # A regression must fail, not leave the modal event loop hanging.
            next(
                button
                for button in box.buttons()
                if box.buttonRole(button) == QMessageBox.ButtonRole.DestructiveRole
            ).click()

    QTimer.singleShot(0, finish_other_import)
    students._apply_import(parse_students_csv("Name,Coordinates\nDiscard me,bad point\n"))
    assert not session.students
    assert [row.name for row in session.locations] == ["Keep this site"]


def _ready_then_failed(window):
    session = window.controller.session
    project = session.build_project().project
    outcome = solve_project(project)
    session.mark_result()
    window.pages[4].show_outcome(outcome, project)
    for index in range(len(session.locations)):
        session.update_location(index, capacity="0")
    window.controller.notify()
    failed_project = session.build_project().project
    failed = solve_project(failed_project)
    return outcome, project, failed, failed_project


def test_export_keeps_selected_previous_snapshot_while_dialog_is_open(ready_window, tmp_path):
    window = ready_window
    old, _project, failed, failed_project = _ready_then_failed(window)
    target = tmp_path / "previous.csv"
    window._confirm_previous_result = lambda _action: True

    def choose_file(*_args):
        # Equivalent to queued SolveWorker completion while QFileDialog.exec runs.
        window.pages[4].show_outcome(failed, failed_project)
        window.refresh_chrome()
        assert not window.export_action.isEnabled()
        return str(target)

    window.ask_save_csv = choose_file
    window.export_results()
    with target.open(newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(old.result.placements)
    assert all(row["location_id"] for row in rows)


def test_print_keeps_selected_snapshot_during_confirmation(ready_window, monkeypatch):
    from placement_optimizer.ui import printing

    window = ready_window
    old, project, failed, failed_project = _ready_then_failed(window)
    selected = []

    def confirm(_action):
        window.pages[4].show_outcome(failed, failed_project)
        return True

    class Preview:
        def __init__(self, outcome, selected_project, _parent, *, previous_result):
            selected.append((outcome, selected_project, previous_result))

        def exec(self):
            return 0

    window._confirm_previous_result = confirm
    monkeypatch.setattr(printing, "ResultsPrintPreviewDialog", Preview)
    window.print_results()
    assert selected == [(old, project, True)]
