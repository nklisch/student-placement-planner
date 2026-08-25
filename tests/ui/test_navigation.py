"""Navigation rail, footer readiness, and goal wiring."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu

from placement_optimizer.optimization import ObjectiveKind
from placement_optimizer.optimization.models import LOWEST_TOTAL_OBJECTIVES
from placement_optimizer.ui.dialogs import AdvancedOptionsDialog


def test_rail_lists_the_five_steps(window) -> None:
    assert window.steps_model.rowCount() == 5
    labels = [window.steps_model.index(row).data() for row in range(5)]
    assert labels == [
        "1   Students",
        "2   Locations",
        "3   Rules",
        "4   Travel times",
        "5   Results",
    ]


def test_rail_selection_switches_pages(window) -> None:
    window.navigate(3)
    assert window.stack.currentIndex() == 3
    window.navigate(0)
    assert window.stack.currentIndex() == 0


def test_footer_tracks_readiness(window, fill_small) -> None:
    assert window.readiness_button.text() == "3 steps need attention"
    fill_small(window.controller)
    assert window.readiness_button.text() == "Ready to find placements"
    assert window.run_button.text() == "Find placements"


def test_run_button_explains_when_not_ready(window, qtbot) -> None:
    window.show()
    window.find_placements()  # not ready: opens the readiness menu instead of solving
    menu = window.findChild(QMenu)
    assert menu is not None
    actions = [action.text() for action in menu.actions()]
    assert any(text.startswith("Students —") for text in actions)
    assert any(text.startswith("Locations —") for text in actions)
    assert any(text.startswith("Travel times —") for text in actions)
    menu.close()


def test_readiness_menu_jumps_to_step(window) -> None:
    window._jump_to_step(3)
    assert window.stack.currentIndex() == 3


def test_step_statuses_follow_session_content(window, fill_small) -> None:
    fill_small(window.controller)
    assert window.steps_model.index(0).data(window.steps_model.STATUS_ROLE) == "✓"
    assert window.steps_model.index(1).data(window.steps_model.STATUS_ROLE) == "✓"
    assert window.steps_model.index(2).data(window.steps_model.STATUS_ROLE) == "0"
    assert window.steps_model.index(3).data(window.steps_model.STATUS_ROLE) == "✓"
    assert window.steps_model.index(4).data(window.steps_model.STATUS_ROLE) == "○"


def test_goal_combo_applies_presets(window) -> None:
    session = window.controller.session
    assert window.goal_combo.currentText() == "Fair commute (recommended)"

    index = window.goal_combo.findText("Lowest total driving")
    window._goal_activated(index)
    assert session.optimization.objectives == LOWEST_TOTAL_OBJECTIVES
    assert window.goal_combo.currentText() == "Lowest total driving"


def test_goal_combo_shows_custom_after_manual_ordering(window) -> None:
    session = window.controller.session
    session.set_optimization(
        replace(
            session.optimization,
            objectives=(ObjectiveKind.TOTAL_COMMUTE, ObjectiveKind.MAXIMUM_COMMUTE),
        )
    )
    window.controller.notify()
    assert window.goal_combo.currentText() == "Custom"


def test_advanced_options_round_trip(qtbot) -> None:
    from placement_optimizer.optimization import OptimizationConfig

    dialog = AdvancedOptionsDialog(OptimizationConfig(), None)
    dialog.target_spin.setValue(45)
    dialog.limit_spin.setValue(10)
    dialog.unassigned_check.setChecked(True)
    config = dialog.config()
    assert config.commute_target_seconds == 45 * 60
    assert config.time_limit_seconds == 10.0
    assert config.allow_unassigned is True
    assert config.objectives == OptimizationConfig().objectives

    dialog._restore_defaults()
    assert dialog.config() == OptimizationConfig()


def test_custom_shortcuts_use_qt_portable_command_modifier() -> None:
    import placement_optimizer.ui.mainwindow as mainwindow_module

    sequences = mainwindow_module.MainWindow._primary_shortcuts("1", "+")
    rendered = [
        sequence.toString(QKeySequence.SequenceFormat.PortableText) for sequence in sequences
    ]
    # Qt maps portable Ctrl to the Command key on macOS.
    assert rendered == ["Ctrl+1", "Ctrl++"]


def test_add_row_supports_equals_and_plus_shortcuts(window) -> None:
    rendered = {
        sequence.toString(QKeySequence.SequenceFormat.PortableText)
        for sequence in window.add_row_action.shortcuts()
    }
    assert rendered == {"Ctrl+=", "Ctrl++"}


def test_results_step_quiet_before_first_run(window) -> None:
    results = window.pages[4]
    assert results.outcome is None
    assert results.stack.currentIndex() == 0
