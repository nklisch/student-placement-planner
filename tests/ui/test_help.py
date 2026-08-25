"""Contextual field help, user guide, and optional walkthrough."""

from __future__ import annotations

from PySide6.QtCore import Qt

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
