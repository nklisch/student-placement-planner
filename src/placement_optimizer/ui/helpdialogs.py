"""In-app user guide and optional, modeless walkthrough."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from placement_optimizer.ui.help_content import HELP_TOPICS, WALKTHROUGH_STEPS, HelpTopic
from placement_optimizer.ui.widgets import make_label


class HelpCenterDialog(QDialog):
    """A local, topic-based help reference with plain-language guidance."""

    def __init__(self, parent: QWidget | None = None, *, initial_topic: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("User guide")
        self.setModal(False)
        self.setMinimumSize(760, 520)
        self.resize(820, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = make_label("Student Placement Optimizer guide", role="title")
        layout.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.topics = QListWidget()
        self.topics.setAccessibleName("Help topics")
        self.topics.setFixedWidth(185)
        for topic in HELP_TOPICS:
            self.topics.addItem(topic.title)
        body.addWidget(self.topics)

        self.pages = QStackedWidget()
        for topic in HELP_TOPICS:
            self.pages.addWidget(self._build_topic(topic))
        body.addWidget(self.pages, stretch=1)
        layout.addLayout(body, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.topics.currentRowChanged.connect(self.pages.setCurrentIndex)
        selected = min(max(initial_topic, 0), len(HELP_TOPICS) - 1)
        self.topics.setCurrentRow(selected)

    @staticmethod
    def _build_topic(topic: HelpTopic) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 4, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(make_label(topic.title, role="title"))
        introduction = make_label(topic.introduction, role="secondary", wrap=True)
        layout.addWidget(introduction)

        for entry in topic.entries:
            entry_box = QFrame()
            entry_box.setProperty("card", "true")
            entry_layout = QVBoxLayout(entry_box)
            entry_layout.setContentsMargins(14, 10, 14, 10)
            entry_layout.setSpacing(3)
            entry_layout.addWidget(make_label(entry.heading, role="heading", wrap=True))
            entry_layout.addWidget(make_label(entry.body, wrap=True))
            layout.addWidget(entry_box)
        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll


class GuidedWalkthroughDialog(QDialog):
    """A modeless guide that moves the main window through its five real pages."""

    openUserGuide = Signal()

    def __init__(
        self,
        navigate: Callable[[int], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._navigate = navigate
        self._step = 0

        self.setWindowTitle("Guided walkthrough")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setMinimumWidth(440)
        self.resize(480, 310)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.progress_label = make_label("", role="secondary")
        layout.addWidget(self.progress_label)
        self.title_label = make_label("", role="title", wrap=True)
        layout.addWidget(self.title_label)
        self.body_label = make_label("", wrap=True)
        layout.addWidget(self.body_label)

        tip_box = QFrame()
        tip_box.setProperty("banner", "info")
        tip_layout = QVBoxLayout(tip_box)
        tip_layout.setContentsMargins(12, 9, 12, 9)
        tip_layout.setSpacing(3)
        tip_layout.addWidget(make_label("Try this", role="heading"))
        self.tip_label = make_label("", wrap=True)
        tip_layout.addWidget(self.tip_label)
        layout.addWidget(tip_box)
        layout.addStretch(1)

        actions = QHBoxLayout()
        guide_button = QPushButton("Open full guide")
        guide_button.setProperty("kind", "quiet")
        guide_button.clicked.connect(self._open_guide)
        actions.addWidget(guide_button)
        actions.addStretch(1)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.previous_step)
        self.next_button = QPushButton("Next")
        self.next_button.setProperty("kind", "primary")
        self.next_button.clicked.connect(self.next_step)
        actions.addWidget(self.back_button)
        actions.addWidget(self.next_button)
        layout.addLayout(actions)

        self.setAccessibleName("Guided walkthrough")
        self.setAccessibleDescription(
            "An optional five-step guide that points to each page without changing project data."
        )
        self.set_step(0)

    @property
    def current_step(self) -> int:
        return self._step

    def restart(self) -> None:
        self.set_step(0)

    def set_step(self, index: int) -> None:
        self._step = min(max(index, 0), len(WALKTHROUGH_STEPS) - 1)
        step = WALKTHROUGH_STEPS[self._step]
        self.progress_label.setText(f"Step {self._step + 1} of {len(WALKTHROUGH_STEPS)}")
        self.title_label.setText(step.title)
        self.body_label.setText(step.body)
        self.tip_label.setText(step.try_this)
        self.back_button.setEnabled(self._step > 0)
        self.next_button.setText("Done" if self._step == len(WALKTHROUGH_STEPS) - 1 else "Next")
        self._navigate(step.page_index)

    def previous_step(self) -> None:
        if self._step > 0:
            self.set_step(self._step - 1)

    def next_step(self) -> None:
        if self._step == len(WALKTHROUGH_STEPS) - 1:
            self.accept()
        else:
            self.set_step(self._step + 1)

    def _open_guide(self) -> None:
        self.close()
        self.openUserGuide.emit()
