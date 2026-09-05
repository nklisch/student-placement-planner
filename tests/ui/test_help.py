"""Contextual field help, user guide, and optional walkthrough."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from placement_optimizer.projects.csv_io import (
    parse_locations_csv,
    parse_matrix_csv,
    parse_students_csv,
)
from placement_optimizer.ui.help_content import HELP_TOPICS, WALKTHROUGH_STEPS
from placement_optimizer.ui.helpdialogs import GuidedWalkthroughDialog, HelpCenterDialog


def test_roster_column_headings_explain_fields(window) -> None:
    students = window.pages[0].model
    locations = window.pages[1].model

    student_id_help = students.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    capacity_help = locations.headerData(2, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    minimum_help = locations.headerData(3, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)

    assert "short code" in student_id_help.lower()
    assert "most students" in capacity_help.lower()
    assert "leave blank" in minimum_help.lower()


def test_help_center_contains_plain_language_topics(qtbot) -> None:
    dialog = HelpCenterDialog()
    qtbot.addWidget(dialog)

    assert dialog.topics.count() == len(HELP_TOPICS)
    assert dialog.pages.count() == len(HELP_TOPICS)
    assert dialog.topics.item(0).text() == "Quick start"
    assert dialog.topics.item(dialog.topics.count() - 1).text() == "Spreadsheet tips"

    dialog.topics.setCurrentRow(3)
    assert dialog.pages.currentIndex() == 3


def test_walkthrough_moves_through_real_page_numbers(qtbot) -> None:
    visited: list[int] = []
    dialog = GuidedWalkthroughDialog(visited.append)
    qtbot.addWidget(dialog)

    assert visited == [0]
    assert dialog.current_step == 0
    assert not dialog.back_button.isEnabled()

    dialog.next_step()
    assert dialog.current_step == 1
    assert visited[-1] == 1

    dialog.set_step(len(WALKTHROUGH_STEPS) - 1)
    assert dialog.next_button.text() == "Done"
    assert visited[-1] == 4


def test_main_window_exposes_guide_and_modeless_walkthrough(window) -> None:
    help_menu = window.menuBar().actions()[-1].menu()
    labels = [action.text() for action in help_menu.actions()]
    assert labels[:2] == ["User guide…", "Guided walkthrough…"]

    window.navigate(3)
    window.show_guided_walkthrough()
    walkthrough = window._walkthrough
    assert walkthrough is not None
    assert walkthrough.isVisible()
    assert window.stack.currentIndex() == 0

    walkthrough.next_step()
    assert window.stack.currentIndex() == 1
    walkthrough.close()

    window.show_user_guide()
    assert window._help_center is not None
    assert window._help_center.isVisible()
    assert window.isEnabled()  # The guide remains open while users work in the main window.


def test_rule_actions_and_footer_have_practical_tooltips(window) -> None:
    rules = window.pages[2]
    actions = rules.add_button.menu().actions()

    assert all(action.toolTip() for action in actions)
    assert "required inputs" in window.readiness_button.toolTip()
    assert "longest drive" in window.goal_combo.toolTip()


def test_help_explains_reusable_work_and_import_semantics() -> None:
    topics = {topic.title: topic for topic in HELP_TOPICS}
    save = topics["Save, open, and share"]
    save_text = save.introduction + " ".join(entry.body for entry in save.entries)
    assert "no automatic roster save" in save_text
    assert ".spp" in save_text
    assert "File → Open" in save_text
    assert "Neither restores your editable project" in save_text

    imports = topics["CSV imports"]
    assert "append" in imports.introduction
    text = " ".join(entry.body for entry in imports.entries)
    assert "Name,ID,Capacity,Minimum,Address,Coordinates" in text
    assert "student_id,location_id,driving_minutes,distance_km" in text
    assert "including blanks" in text


def test_help_distinguishes_preferences_limits_and_global_undo() -> None:
    text = " ".join(entry.body for topic in HELP_TOPICS for entry in topic.entries)
    assert "individual limit overrides the general limit" in text
    assert "it does not forbid them" in text
    assert "Choices first minimizes the sum" in text
    assert "even on another page" in text
    assert "Coordinates take precedence" in text


def test_downloadable_csv_examples_are_complete_and_match() -> None:
    examples = Path(__file__).resolve().parents[2] / "docs" / "examples"
    students = parse_students_csv((examples / "students.csv").read_text())
    locations = parse_locations_csv((examples / "locations.csv").read_text())
    travel = parse_matrix_csv((examples / "travel-times.csv").read_text())
    assert not students.issues
    assert not locations.issues
    assert not travel.issues
    assert len(students.items) == len(locations.items) == 2
    assert sum(location.capacity for location in locations.items) == len(students.items)
    assert {(entry.student_id, entry.location_id) for entry in travel.items} == {
        (student.id, location.id) for student in students.items for location in locations.items
    }
    assert all(entry.duration_seconds is not None for entry in travel.items)
