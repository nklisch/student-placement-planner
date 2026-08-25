"""Core table model behavior: live new row, validation styling, paste, undo."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt

from placement_optimizer.application import DraftArea
from placement_optimizer.optimization import AssignmentRules, GroupRule, Preference
from placement_optimizer.ui.tablemodels import LocationsTableModel, StudentsTableModel
from placement_optimizer.ui.tableview import PasteTableView

EDIT = Qt.ItemDataRole.EditRole
DISPLAY = Qt.ItemDataRole.DisplayRole
BACKGROUND = Qt.ItemDataRole.BackgroundRole
TOOLTIP = Qt.ItemDataRole.ToolTipRole


def test_live_new_row_creates_student_with_auto_id(controller) -> None:
    model = StudentsTableModel(controller)
    assert model.rowCount() == 1  # only the live new row

    ghost = model.index(0, 0)
    assert model.setData(ghost, "Alice", EDIT)

    session = controller.session
    assert len(session.students) == 1
    assert session.students[0].name == "Alice"
    assert session.students[0].id == "S001"
    assert model.rowCount() == 2  # real row plus a fresh live row


def test_invalid_capacity_is_tinted_with_tooltip_and_raw_text_kept(controller) -> None:
    model = LocationsTableModel(controller)
    model.setData(model.index(0, 0), "Library", EDIT)

    capacity_index = model.index(0, 2)
    model.setData(capacity_index, "many", EDIT)

    assert controller.session.locations[0].capacity == "many"
    assert model.data(capacity_index, DISPLAY) == "many"
    assert model.data(capacity_index, BACKGROUND) is not None
    assert "whole number" in model.data(capacity_index, TOOLTIP)


def test_missing_required_value_gets_the_amber_treatment(controller) -> None:
    model = LocationsTableModel(controller)
    model.setData(model.index(0, 0), "Library", EDIT)

    capacity_index = model.index(0, 2)
    # Blank capacity: an unresolved amber cell, not an alarm-red one.
    assert controller.session.locations[0].capacity == ""
    background = model.data(capacity_index, BACKGROUND)
    assert background is not None
    tooltip = model.data(capacity_index, TOOLTIP)
    assert "required" in tooltip.lower()


def test_paste_block_appends_rows_and_is_one_undo_step(controller) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1\t1 Main Street\nBob\ts2\t2 High Street")

    assert [row.name for row in controller.session.students] == ["Alice", "Bob"]
    assert [row.id for row in controller.session.students] == ["s1", "s2"]

    assert model.undo.undo()
    assert controller.session.students == []
    assert model.undo.redo()
    assert [row.name for row in controller.session.students] == ["Alice", "Bob"]


def test_pasted_split_coordinates_merge_into_the_combined_column(controller) -> None:
    model = StudentsTableModel(controller)
    # Excel export with separate latitude/longitude columns pasted at Name.
    model.paste_block(0, 0, "Alice\ts1\t1 Main Street\t51.5\t-0.12")

    row = controller.session.students[0]
    assert row.coordinates == "51.5, -0.12"
    readiness = controller.session.readiness()
    assert not [i for i in readiness.issues if i.row_key == row.key]


def test_invalid_pasted_cells_land_and_are_marked(controller) -> None:
    model = LocationsTableModel(controller)
    model.paste_block(0, 0, "Library\tl1\tnot-a-number")

    row = controller.session.locations[0]
    assert row.capacity == "not-a-number"
    issues = controller.session.readiness().issues
    assert any(issue.area is DraftArea.LOCATIONS and issue.row_key == row.key for issue in issues)


def test_clear_cells_and_undo_restores(controller) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1")

    model.clear_indexes([model.index(0, 0), model.index(0, 1)])
    assert controller.session.students[0].name == ""
    assert controller.session.students[0].id == ""

    assert model.undo.undo()
    assert controller.session.students[0].name == "Alice"
    assert controller.session.students[0].id == "s1"


def test_deleting_a_referenced_row_cleans_rules_and_undo_restores_both(controller) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1\nBob\ts2")
    session = controller.session
    session.set_rules(
        AssignmentRules(
            preferences=(Preference("s1", ("l1",)),),
            together=(GroupRule(("s1", "s2")),),
        )
    )

    rules_cleaned = model.delete_rows([0])
    assert rules_cleaned is True
    assert [row.id for row in session.students] == ["s2"]
    assert session.rules.preferences == ()
    assert session.rules.together == ()

    assert model.undo.undo()
    assert [row.id for row in session.students] == ["s1", "s2"]
    assert session.rules.preferences == (Preference("s1", ("l1",)),)
    assert session.rules.together == (GroupRule(("s1", "s2")),)


def test_enter_navigation_moves_current_cell_down(controller, qapp) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1\nBob\ts2")
    view = PasteTableView()
    view.setModel(model)
    view.setCurrentIndex(model.index(0, 0))

    view.move_cursor_down()

    assert view.currentIndex() == model.index(1, 0)


def test_view_copy_produces_excel_ready_tsv(controller, qapp) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1\nBob\ts2")
    view = PasteTableView()
    view.setModel(model)
    view.selectAll()

    view.copy_selection()

    from PySide6.QtGui import QGuiApplication

    text = QGuiApplication.clipboard().text()
    assert text.splitlines()[0].split("\t")[:2] == ["Alice", "s1"]
    assert text.splitlines()[1].split("\t")[:2] == ["Bob", "s2"]


def test_view_delete_key_clears_selection(controller, qtbot) -> None:
    model = StudentsTableModel(controller)
    model.paste_block(0, 0, "Alice\ts1")
    view = PasteTableView()
    qtbot.addWidget(view)
    view.setModel(model)
    view.setCurrentIndex(model.index(0, 0))
    view.selectionModel().select(
        model.index(0, 0),
        view.selectionModel().SelectionFlag.Select,
    )

    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)

    assert controller.session.students[0].name == ""
