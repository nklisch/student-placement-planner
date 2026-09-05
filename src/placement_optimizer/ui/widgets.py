"""Small shared widgets: banners, stat cards, empty states, toasts, mode cards."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def make_label(text: str, *, role: str | None = None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    if wrap:
        label.setWordWrap(True)
    return label


def clear_layout(layout) -> None:
    """Remove and delete every widget nested inside a layout."""

    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class Banner(QFrame):
    """A tinted outcome banner: kind is success, warning, error, or info."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("banner", "info")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        self.title = make_label("", role="heading", wrap=True)
        self.detail = make_label("", wrap=True)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        self.detail.hide()

    def show_message(self, kind: str, title: str, detail: str = "") -> None:
        self.setProperty("banner", kind)
        # Re-polish so the new banner property takes effect in QSS.
        self.style().unpolish(self)
        self.style().polish(self)
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.show()


class StatCard(QFrame):
    """A quiet statistic card with a small caption and a large value."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.value_label = make_label("—", role="stat")
        caption_label = make_label(caption, role="secondary")
        layout.addWidget(self.value_label)
        layout.addWidget(caption_label)
        self.setAccessibleName(caption)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class EmptyState(QFrame):
    """A centered surface shown until a step has content."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        self.title_label = make_label(title, role="title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.title_label)
        self.actions = QVBoxLayout()
        self.actions.setSpacing(8)
        self.actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addLayout(self.actions)
        outer.addStretch(1)

    def add_action(self, text: str, callback: Callable[[], None], *, quiet: bool = False) -> None:
        button = QPushButton(text)
        if quiet:
            button.setProperty("kind", "quiet")
        button.clicked.connect(callback)
        button.setMinimumHeight(28)
        self.actions.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)


class Toast(QFrame):
    """A temporary bottom-right notice with an optional action (usually Undo)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(12)
        self.message = make_label("")
        self.action_button = QPushButton("")
        self.action_button.setProperty("kind", "quiet")
        self.action_button.hide()
        self._action: Callable[[], None] | None = None
        layout.addWidget(self.message)
        layout.addWidget(self.action_button)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self.action_button.clicked.connect(self._invoke_action)
        self._timer.timeout.connect(self._dismiss)
        self.hide()

    def show_message(
        self,
        text: str,
        action_text: str = "",
        action: Callable[[], None] | None = None,
        *,
        duration_ms: int = 6000,
    ) -> None:
        self.message.setText(text)
        self._action = None
        if action_text and action is not None:
            self.action_button.setText(action_text)
            self._action = action
            self.action_button.setEnabled(True)
            self.action_button.show()
        else:
            self.action_button.hide()
        self.adjustSize()
        parent = self.parentWidget()
        margin = 16
        self.move(
            max(margin, parent.width() - self.width() - margin),
            max(margin, parent.height() - self.height() - margin - 56),
        )
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _dismiss(self) -> None:
        self._action = None
        self.action_button.setEnabled(False)
        self._timer.stop()
        self.hide()

    def _invoke_action(self) -> None:
        # Clear before calling: reentrant/double clicks must not consume older history.
        action = self._action
        self._dismiss()
        if action is not None:
            action()


class ModeCard(QFrame):
    """A selectable travel-mode card with a radio indicator."""

    def __init__(
        self,
        title: str,
        description: str,
        on_selected: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        from PySide6.QtWidgets import QRadioButton

        self.radio = QRadioButton(title)
        self.radio.setProperty("role", "heading")
        self.description = make_label(description, role="secondary", wrap=True)
        self.description.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.radio)
        layout.addWidget(self.description)
        self.radio.toggled.connect(lambda checked: checked and on_selected())
        self.setToolTip(description)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            self.radio.setFocus(Qt.FocusReason.MouseFocusReason)
            self.radio.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def is_selected(self) -> bool:
        return self.radio.isChecked()

    def select(self) -> None:
        self.radio.setChecked(True)


class InfoStrip(QFrame):
    """A slim information strip used for capacity notes and similar hints."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("banner", "info")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self.label = make_label("", wrap=True)
        layout.addWidget(self.label)
        self.hide()

    def show_text(self, text: str) -> None:
        self.label.setText(text)
        self.setVisible(bool(text))
