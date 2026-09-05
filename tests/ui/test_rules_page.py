"""Rules page: sentence cards, native dialogs, deletion undo."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QLabel

from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    Preference,
    StudentLocationPair,
)
from placement_optimizer.ui.pages.ruledialogs import (
    AllowedLocationsDialog,
    CommuteLimitDialog,
    GroupRuleDialog,
    PairRuleDialog,
    RankedChoicesDialog,
)

STUDENTS = [("s1", "Aisha"), ("s2", "Mateo"), ("s3", "Ana")]
LOCATIONS = [("l1", "North Clinic"), ("l2", "Riverside")]


def _card_texts(page) -> list[str]:
    texts = []
    for index in range(page.cards_layout.count()):
        widget = page.cards_layout.itemAt(index).widget()
        if widget is not None:
            for label in widget.findChildren(QLabel):
                texts.append(label.text())
    return texts


def test_empty_copy_and_rule_count(named_window) -> None:
    page = named_window.pages[2]
    assert page.rule_count() == 0

    page._apply_rules(
        AssignmentRules(
            preferences=(Preference("s1", ("l1", "l2")),),
            together=(GroupRule(("s2", "s3")),),
            pinned=(StudentLocationPair("s1", "l1"),),
            prohibited=(StudentLocationPair("s2", "l2"),),
            maximum_commute_seconds=45 * 60,
            eligible_locations=(Preference("s3", ("l1",)),),
        )
    )
    assert page.rule_count() == 6

    sentences = " ".join(_card_texts(page))
    assert "Aisha prefers 1. North Clinic, 2. Riverside." in sentences
    assert "Mateo and Ana are placed at the same location." in sentences
    assert "Aisha must be placed at North Clinic." in sentences
    assert "Mateo is not allowed at Riverside." in sentences
    assert "Nobody drives more than 45 minutes." in sentences
    assert "Ana can only go to North Clinic." in sentences


def test_delete_rule_is_undoable(named_window) -> None:
    page = named_window.pages[2]
    page._apply_rules(AssignmentRules(together=(GroupRule(("s2", "s3")),)))

    toasts = []
    named_window.show_toast = lambda text, action_text="", action=None: toasts.append(
        (text, action_text, action)
    )
    page._delete_entry("together", 0)
    assert page.rule_count() == 0
    assert toasts and toasts[0][0] == "Rule deleted."

    # The toast action restores the rule.
    toasts[0][2]()
    assert page.rule_count() == 1


def test_ranked_choices_dialog_compacts_and_dedupes(qtbot) -> None:
    dialog = RankedChoicesDialog(STUDENTS, LOCATIONS, (Preference("s1", ("l1",)),))
    model = dialog._model

    # Aisha keeps North Clinic; add Riverside as her second choice.
    model.setData(model.index(0, 2), "l2", Qt.ItemDataRole.EditRole)
    # Mateo picks Riverside twice: the duplicate collapses.
    model.setData(model.index(1, 1), "l2", Qt.ItemDataRole.EditRole)
    model.setData(model.index(1, 2), "l2", Qt.ItemDataRole.EditRole)

    assert dialog.preferences() == (
        Preference("s1", ("l1", "l2")),
        Preference("s2", ("l2",)),
    )


def test_group_dialog_requires_two_students(qtbot) -> None:
    dialog = GroupRuleDialog("Keep students together", STUDENTS)
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog._list.item(0).setCheckState(Qt.CheckState.Checked)
    assert not ok.isEnabled()
    dialog._list.item(1).setCheckState(Qt.CheckState.Checked)
    assert ok.isEnabled()
    assert dialog.selected_ids() == ("s1", "s2")


def test_pair_dialog_prefills_existing(qtbot) -> None:
    dialog = PairRuleDialog(
        "Pin a placement", "Must be placed here.", STUDENTS, LOCATIONS, "s2", "l1"
    )
    assert dialog.pair() == ("s2", "l1")


def test_commute_dialog_global_and_per_student(qtbot) -> None:
    dialog = CommuteLimitDialog(STUDENTS, 45 * 60, (("s1", 20 * 60),))
    maximum, limits = dialog.result_limits()
    assert maximum == 45 * 60
    assert limits == (("s1", 20 * 60),)

    dialog.global_check.setChecked(False)
    maximum, limits = dialog.result_limits()
    assert maximum is None


def test_allowed_locations_all_checked_means_anywhere(qtbot) -> None:
    dialog = AllowedLocationsDialog(STUDENTS, LOCATIONS, (Preference("s1", ("l1",)),))
    # s1 starts restricted to North Clinic.
    checks = {check.property("location_id"): check for check in dialog._checks}
    assert checks["l1"].isChecked()
    assert not checks["l2"].isChecked()

    # Checking everything removes the restriction entirely.
    checks["l2"].setChecked(True)
    assert dialog.eligible() == ()

    # Restricting again produces exactly the checked set.
    checks["l2"].setChecked(False)
    assert dialog.eligible() == (Preference("s1", ("l1",)),)


def test_student_limits_add_unused_and_reject_duplicates(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = CommuteLimitDialog(STUDENTS, 2700, (("s1", 1200),))
    qtbot.addWidget(dialog)
    model = dialog._limits_model
    model.add_row()
    assert model.limits() == (("s1", 1200), ("s2", 1800))
    model.setData(model.index(1, 0), "s1")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog.accept()
    assert warnings
    assert dialog.result() == 0
    model.setData(model.index(1, 0), "s3")
    dialog.accept()
    assert dialog.result() == 1
    assert "override" in dialog.global_spin.toolTip()


def test_empty_allowed_requires_confirmation_and_preserves_none(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = AllowedLocationsDialog(STUDENTS, LOCATIONS, ())
    qtbot.addWidget(dialog)
    for check in dialog._checks:
        check.setChecked(False)
    assert not dialog.empty_warning.isHidden()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog.accept()
    assert dialog.result() == 0
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog.accept()
    assert dialog.result() == 1
    assert dialog.eligible() == (Preference("s1", ()),)


def test_empty_allowed_card_explains_consequence(named_window):
    page = named_window.pages[2]
    page._apply_rules(AssignmentRules(eligible_locations=(Preference("s1", ()),)))
    assert "No locations allowed — Aisha cannot be placed." in _card_texts(page)


def test_rules_share_global_history_and_require_unambiguous_ids(named_window):
    from dataclasses import replace

    page = named_window.pages[2]
    session = named_window.controller.session
    assert page.undo is named_window.controller.undo
    page._apply_rules(AssignmentRules(maximum_commute_seconds=1200))
    page.undo.undo()
    assert session.rules.maximum_commute_seconds is None
    page.undo.redo()
    assert session.rules.maximum_commute_seconds == 1200
    original = session.students[1]
    session.students[1] = replace(original, id=session.students[0].id)
    named_window.controller.notify()
    assert not page.add_button.isEnabled()
    session.students[1] = replace(original, name="")
    named_window.controller.notify()
    assert page.add_button.isEnabled()


def test_rule_combo_displays_names_but_stores_ids(qtbot):
    from PySide6.QtWidgets import QWidget

    from placement_optimizer.ui.pages.ruledialogs import _ComboDelegate

    parent = QWidget()
    qtbot.addWidget(parent)
    combo = _ComboDelegate(STUDENTS).createEditor(parent, None, None)
    assert combo.itemText(1) == "Aisha"
    assert combo.itemData(1) == "s1"
