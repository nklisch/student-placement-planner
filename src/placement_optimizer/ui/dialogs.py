"""Advanced goal options, troubleshooting details, and About dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.optimization import ObjectiveKind, OptimizationConfig

OBJECTIVE_LABELS = {
    ObjectiveKind.UNASSIGNED_COUNT: "Fewest unplaced students",
    ObjectiveKind.MAXIMUM_COMMUTE: "Smallest longest drive",
    ObjectiveKind.OVER_TARGET_COUNT: "Fewest students over the target",
    ObjectiveKind.TOTAL_COMMUTE: "Lowest total driving",
    ObjectiveKind.PREFERENCE_PENALTY: "Best match to ranked choices",
    ObjectiveKind.ASSIGNMENT_CHANGES: "Fewest changes from previous placements",
}


class AdvancedOptionsDialog(QDialog):
    """Ordered goals, commute target, calculation time, and unplaced students."""

    def __init__(self, config: OptimizationConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("More options")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        goals_label = QLabel(
            "Goals, in order. The first goal is made as good as possible before the next begins."
        )
        goals_label.setProperty("role", "secondary")
        goals_label.setWordWrap(True)
        layout.addWidget(goals_label)

        goals_row = QHBoxLayout()
        self.goals_list = QListWidget()
        self.goals_list.setToolTip(
            "The first goal has highest priority. It is made as good as possible before "
            "the next goal begins."
        )
        self.goals_list.setAccessibleName("Goals in order")
        for objective in config.objectives:
            item = QListWidgetItem(OBJECTIVE_LABELS[objective])
            item.setData(Qt.ItemDataRole.UserRole, objective)
            self.goals_list.addItem(item)
        self.goals_list.setMaximumWidth(320)
        goals_row.addWidget(self.goals_list)
        move_column = QVBoxLayout()
        up_button = QToolButton()
        up_button.setText("Up")
        up_button.setToolTip("Give the selected goal higher priority.")
        up_button.clicked.connect(lambda: self._move(-1))
        down_button = QToolButton()
        down_button.setText("Down")
        down_button.setToolTip("Give the selected goal lower priority.")
        down_button.clicked.connect(lambda: self._move(1))
        move_column.addWidget(up_button)
        move_column.addWidget(down_button)
        move_column.addStretch(1)
        goals_row.addLayout(move_column)
        layout.addLayout(goals_row)

        form = QFormLayout()
        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, 999)
        self.target_spin.setSuffix(" minutes")
        self.target_spin.setToolTip(
            "The Fair commute goal tries to keep as few students as possible above this drive."
        )
        self.target_spin.setValue(round(config.commute_target_seconds / 60))
        form.addRow("Commute target", self.target_spin)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 600)
        self.limit_spin.setSuffix(" seconds")
        self.limit_spin.setToolTip(
            "How long the app may spend improving placements before returning the best "
            "valid result found."
        )
        self.limit_spin.setValue(round(config.time_limit_seconds))
        form.addRow("Calculation time limit", self.limit_spin)
        self.unassigned_check = QCheckBox("Allow students to be left unplaced")
        self.unassigned_check.setToolTip(
            "Use only when a partial result is useful. The app still leaves as few "
            "students unplaced as possible."
        )
        self.unassigned_check.setChecked(config.allow_unassigned)
        form.addRow("", self.unassigned_check)
        layout.addLayout(form)

        restore = QToolButton()
        restore.setText("Restore defaults")
        restore.clicked.connect(self._restore_defaults)
        layout.addWidget(restore, alignment=Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _move(self, direction: int) -> None:
        row = self.goals_list.currentRow()
        target = row + direction
        if row < 0 or not 0 <= target < self.goals_list.count():
            return
        item = self.goals_list.takeItem(row)
        self.goals_list.insertItem(target, item)
        self.goals_list.setCurrentRow(target)

    def _restore_defaults(self) -> None:
        defaults = OptimizationConfig()
        self.goals_list.clear()
        for objective in defaults.objectives:
            item = QListWidgetItem(OBJECTIVE_LABELS[objective])
            item.setData(Qt.ItemDataRole.UserRole, objective)
            self.goals_list.addItem(item)
        self.target_spin.setValue(round(defaults.commute_target_seconds / 60))
        self.limit_spin.setValue(round(defaults.time_limit_seconds))
        self.unassigned_check.setChecked(defaults.allow_unassigned)

    def config(self) -> OptimizationConfig:
        objectives = tuple(
            self.goals_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.goals_list.count())
        )
        return OptimizationConfig(
            objectives=objectives,
            commute_target_seconds=self.target_spin.value() * 60,
            time_limit_seconds=float(self.limit_spin.value()),
            allow_unassigned=self.unassigned_check.isChecked(),
        )


class TroubleshootingDialog(QDialog):
    """A small read-only panel: version, OS, travel mode, pack, last detail.

    It structurally excludes student data and keys—only sanitized state that
    helps diagnose a failed operation.
    """

    def __init__(
        self,
        version: str,
        os_description: str,
        travel_mode: str,
        pack_description: str,
        last_detail: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Troubleshooting details")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        form = QFormLayout()
        form.addRow("Application version", QLabel(version))
        form.addRow("Operating system", QLabel(os_description))
        form.addRow("Travel mode", QLabel(travel_mode))
        form.addRow("Offline map pack", QLabel(pack_description))
        layout.addLayout(form)
        detail_label = QLabel("Last technical detail")
        detail_label.setProperty("role", "secondary")
        layout.addWidget(detail_label)
        detail = QLabel(last_detail or "Nothing to report.")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)


class AboutDialog(QDialog):
    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Student Placement Optimizer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        title = QLabel("Student Placement Optimizer")
        title.setProperty("role", "title")
        layout.addWidget(title)
        layout.addWidget(QLabel(f"Version {version}"))
        description = QLabel(
            "A small local utility that assigns students to placement locations, "
            "respecting capacities and rules while keeping drives short. Your data "
            "stays on this computer."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
