"""Rules page: optional constraints shown as concise sentence cards."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.optimization import (
    AssignmentRules,
    GroupRule,
    StudentLocationPair,
)
from placement_optimizer.ui.controller import SessionController, SnapshotUndo
from placement_optimizer.ui.help_content import RULE_ACTION_HELP
from placement_optimizer.ui.pages.ruledialogs import (
    AllowedLocationsDialog,
    CommuteLimitDialog,
    GroupRuleDialog,
    PairRuleDialog,
    RankedChoicesDialog,
)
from placement_optimizer.ui.widgets import make_label

if TYPE_CHECKING:
    from placement_optimizer.ui.mainwindow import MainWindow

EMPTY_COPY = "Most placements need no rules at all. Add one only when something must be true."


def _names(ids: tuple[str, ...] | list[str], lookup: dict[str, str]) -> str:
    labels = [lookup.get(value, value) or value for value in ids]
    if len(labels) <= 2:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _minutes(seconds: int) -> str:
    value = seconds / 60
    return f"{value:g}"


class RuleCard(QFrame):
    def __init__(self, sentence: str, on_edit, on_delete, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 8, 10)
        layout.setSpacing(4)
        label = make_label(sentence, wrap=True)
        layout.addWidget(label, stretch=1)
        edit_button = QToolButton(self)
        edit_button.setText("Edit")
        edit_button.setToolTip("Change this rule.")
        edit_button.clicked.connect(lambda _checked=False: on_edit())
        delete_button = QToolButton(self)
        delete_button.setText("Delete")
        delete_button.setToolTip("Remove this rule. You can undo the deletion.")
        delete_button.clicked.connect(lambda _checked=False: on_delete())
        layout.addWidget(edit_button)
        layout.addWidget(delete_button)
        self.setAccessibleName(f"Rule: {sentence}")


class RulesPage(QWidget):
    def __init__(self, controller: SessionController, host: MainWindow) -> None:
        super().__init__()
        self._controller = controller
        self._host = host
        self.undo = SnapshotUndo(self._capture_rules, self._restore_rules, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.addWidget(make_label("Rules (optional)", role="title"))
        title_block.addWidget(make_label(EMPTY_COPY, role="secondary", wrap=True))
        header.addLayout(title_block, stretch=1)
        layout.addLayout(header)

        self.add_button = QPushButton("Add a rule")
        self.add_button.setToolTip("Add a requirement or a student's ranked choices.")
        menu = QMenu(self.add_button)
        menu.setToolTipsVisible(True)
        for text, handler in (
            ("Ranked choices…", self.add_ranked_choices),
            ("Keep students together…", self.add_together),
            ("Keep students apart…", self.add_apart),
            ("Pin a placement…", self.add_pin),
            ("Not allowed at a location…", self.add_prohibit),
            ("Limit driving time…", self.add_commute_limit),
            ("Allowed locations only…", self.add_allowed_locations),
        ):
            action = menu.addAction(text, handler)
            action.setToolTip(RULE_ACTION_HELP[text])
        self.add_button.setMenu(menu)
        header_row = QHBoxLayout()
        header_row.addWidget(self.add_button)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        layout.addWidget(self.scroll, stretch=1)

        controller.changed.connect(self.refresh_page)
        controller.session_replaced.connect(self._on_session_replaced)
        self.refresh_page()

    # --- session helpers -----------------------------------------------------

    @property
    def _session(self):
        return self._controller.session

    def _capture_rules(self) -> AssignmentRules:
        return self._session.rules

    def _restore_rules(self, rules: AssignmentRules) -> None:
        self._session.set_rules(rules)
        self._controller.notify()

    def _roster(self) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        students = [
            (row.id.strip(), row.name.strip())
            for row in self._session.students
            if row.id.strip() and row.name.strip()
        ]
        locations = [
            (row.id.strip(), row.name.strip())
            for row in self._session.locations
            if row.id.strip() and row.name.strip()
        ]
        return students, locations

    def rule_count(self) -> int:
        rules = self._session.rules
        return (
            len(rules.preferences)
            + len(rules.together)
            + len(rules.separate)
            + len(rules.pinned)
            + len(rules.prohibited)
            + len(rules.eligible_locations)
            + len(rules.student_commute_limits)
            + (1 if rules.maximum_commute_seconds is not None else 0)
        )

    def _apply_rules(self, rules: AssignmentRules, toast: str = "") -> None:
        self._session.set_rules(rules)
        self._controller.notify()
        if toast:
            self._host.show_toast(toast)

    # --- card rendering --------------------------------------------------------

    def refresh_page(self) -> None:
        while self.cards_layout.count() > 1:  # keep the trailing stretch
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        rules = self._session.rules
        students, locations = self._roster()
        student_names = dict(students)
        location_names = dict(locations)

        cards: list[QFrame] = []
        if not self.rule_count():
            empty = make_label(EMPTY_COPY, role="secondary", wrap=True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cards.append(empty)

        for index, preference in enumerate(rules.preferences):
            choices = ", ".join(
                f"{rank}. {location_names.get(lid, lid)}"
                for rank, lid in enumerate(preference.location_ids, start=1)
            )
            cards.append(
                RuleCard(
                    f"{student_names.get(preference.student_id, preference.student_id)} "
                    f"prefers {choices}.",
                    self.add_ranked_choices,
                    lambda i=index: self._delete_entry("preferences", i),
                )
            )
        for index, group in enumerate(rules.together):
            cards.append(
                RuleCard(
                    f"{_names(group.student_ids, student_names)} are placed at the same location.",
                    lambda i=index: self._edit_group("together", i),
                    lambda i=index: self._delete_entry("together", i),
                )
            )
        for index, group in enumerate(rules.separate):
            cards.append(
                RuleCard(
                    f"{_names(group.student_ids, student_names)} are placed at "
                    "different locations.",
                    lambda i=index: self._edit_group("separate", i),
                    lambda i=index: self._delete_entry("separate", i),
                )
            )
        for index, pair in enumerate(rules.pinned):
            cards.append(
                RuleCard(
                    f"{student_names.get(pair.student_id, pair.student_id)} must be placed at "
                    f"{location_names.get(pair.location_id, pair.location_id)}.",
                    lambda i=index: self._edit_pair("pinned", i),
                    lambda i=index: self._delete_entry("pinned", i),
                )
            )
        for index, pair in enumerate(rules.prohibited):
            cards.append(
                RuleCard(
                    f"{student_names.get(pair.student_id, pair.student_id)} is not allowed at "
                    f"{location_names.get(pair.location_id, pair.location_id)}.",
                    lambda i=index: self._edit_pair("prohibited", i),
                    lambda i=index: self._delete_entry("prohibited", i),
                )
            )
        if rules.maximum_commute_seconds is not None:
            cards.append(
                RuleCard(
                    f"Nobody drives more than {_minutes(rules.maximum_commute_seconds)} minutes.",
                    self.add_commute_limit,
                    lambda: self._delete_commute(global_only=True),
                )
            )
        for index, (student_id, seconds) in enumerate(rules.student_commute_limits):
            cards.append(
                RuleCard(
                    f"{student_names.get(student_id, student_id)} drives no more than "
                    f"{_minutes(seconds)} minutes.",
                    self.add_commute_limit,
                    lambda i=index: self._delete_commute(student_index=i),
                )
            )
        for index, entry in enumerate(rules.eligible_locations):
            allowed = _names(entry.location_ids, location_names)
            cards.append(
                RuleCard(
                    f"{student_names.get(entry.student_id, entry.student_id)} can only go to "
                    f"{allowed}.",
                    self.add_allowed_locations,
                    lambda i=index: self._delete_entry("eligible_locations", i),
                )
            )

        for card in cards:
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    # --- add / edit actions -------------------------------------------------------

    def _require_roster(self, need_locations: bool = True) -> bool:
        students, locations = self._roster()
        if not students or (need_locations and not locations):
            self._host.show_toast("Add students and locations before creating rules.")
            return False
        return True

    def add_ranked_choices(self) -> None:
        if not self._require_roster():
            return
        students, locations = self._roster()
        dialog = RankedChoicesDialog(students, locations, self._session.rules.preferences, self)
        if dialog.exec():
            self._apply_rules(
                replace(self._session.rules, preferences=dialog.preferences()),
                "Choices updated.",
            )

    def _add_group(self, attr: str, title: str) -> None:
        if not self._require_roster(need_locations=False):
            return
        students, _ = self._roster()
        dialog = GroupRuleDialog(title, students, parent=self)
        if dialog.exec():
            group = GroupRule(dialog.selected_ids())
            existing = getattr(self._session.rules, attr)
            self._apply_rules(replace(self._session.rules, **{attr: (*existing, group)}))

    def add_together(self) -> None:
        self._add_group("together", "Keep students together")

    def add_apart(self) -> None:
        self._add_group("separate", "Keep students apart")

    def _edit_group(self, attr: str, index: int) -> None:
        students, _ = self._roster()
        group = getattr(self._session.rules, attr)[index]
        title = "Keep students together" if attr == "together" else "Keep students apart"
        dialog = GroupRuleDialog(title, students, group.student_ids, self)
        if dialog.exec():
            groups = list(getattr(self._session.rules, attr))
            groups[index] = GroupRule(dialog.selected_ids())
            self._apply_rules(replace(self._session.rules, **{attr: tuple(groups)}))

    def _add_pair(self, attr: str, title: str, verb: str) -> None:
        if not self._require_roster():
            return
        students, locations = self._roster()
        dialog = PairRuleDialog(title, verb, students, locations, parent=self)
        if dialog.exec():
            pair = StudentLocationPair(*dialog.pair())
            existing = getattr(self._session.rules, attr)
            self._apply_rules(replace(self._session.rules, **{attr: (*existing, pair)}))

    def add_pin(self) -> None:
        self._add_pair("pinned", "Pin a placement", "This student must be placed here.")

    def add_prohibit(self) -> None:
        self._add_pair("prohibited", "Not allowed at a location", "This student cannot go here.")

    def _edit_pair(self, attr: str, index: int) -> None:
        students, locations = self._roster()
        pair = getattr(self._session.rules, attr)[index]
        title = "Pin a placement" if attr == "pinned" else "Not allowed at a location"
        verb = (
            "This student must be placed here."
            if attr == "pinned"
            else "This student cannot go here."
        )
        dialog = PairRuleDialog(
            title, verb, students, locations, pair.student_id, pair.location_id, self
        )
        if dialog.exec():
            pairs = list(getattr(self._session.rules, attr))
            pairs[index] = StudentLocationPair(*dialog.pair())
            self._apply_rules(replace(self._session.rules, **{attr: tuple(pairs)}))

    def add_commute_limit(self) -> None:
        if not self._require_roster(need_locations=False):
            return
        students, _ = self._roster()
        rules = self._session.rules
        dialog = CommuteLimitDialog(
            students, rules.maximum_commute_seconds, rules.student_commute_limits, self
        )
        if dialog.exec():
            maximum, student_limits = dialog.result_limits()
            self._apply_rules(
                replace(
                    rules,
                    maximum_commute_seconds=maximum,
                    student_commute_limits=student_limits,
                )
            )

    def add_allowed_locations(self) -> None:
        if not self._require_roster():
            return
        students, locations = self._roster()
        dialog = AllowedLocationsDialog(
            students, locations, self._session.rules.eligible_locations, self
        )
        if dialog.exec():
            self._apply_rules(replace(self._session.rules, eligible_locations=dialog.eligible()))

    # --- deletion ------------------------------------------------------------

    def _delete_entry(self, attr: str, index: int) -> None:
        self.undo.record()
        entries = list(getattr(self._session.rules, attr))
        del entries[index]
        self._session.set_rules(replace(self._session.rules, **{attr: tuple(entries)}))
        self._controller.notify()
        self._host.show_toast("Rule deleted.", "Undo", self.undo.undo)

    def _delete_commute(self, *, global_only: bool = False, student_index: int = -1) -> None:
        self.undo.record()
        rules = self._session.rules
        if global_only:
            self._session.set_rules(replace(rules, maximum_commute_seconds=None))
        else:
            limits = list(rules.student_commute_limits)
            del limits[student_index]
            self._session.set_rules(replace(rules, student_commute_limits=tuple(limits)))
        self._controller.notify()
        self._host.show_toast("Rule deleted.", "Undo", self.undo.undo)

    def _on_session_replaced(self) -> None:
        self.undo.clear()
        self.refresh_page()
