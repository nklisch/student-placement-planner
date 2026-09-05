"""Focused regression checks for recovery actions and theme contrast."""

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget

from placement_optimizer.ui.theme import DARK, LIGHT, _palette, _qss
from placement_optimizer.ui.widgets import Toast


def _luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def _contrast(a, b):
    low, high = sorted((_luminance(a), _luminance(b)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("tokens", [LIGHT, DARK])
def test_primary_and_selected_text_contrast(tokens):
    # Normal/focus use accent; hover/pressed/checked use accent_pressed.
    for background in ("accent", "accent_pressed"):
        assert _contrast(tokens["accent_text"], tokens[background]) >= 4.5
    assert _contrast(tokens["disabled_text"], tokens["disabled"]) >= 4.5
    assert _contrast(tokens["text"], tokens["accent_soft"]) >= 4.5
    assert (
        _palette(tokens).color(QPalette.ColorRole.HighlightedText).name().upper()
        == tokens["accent_text"]
    )
    assert f"color: {tokens['accent_text']}" in _qss(tokens)


def test_toast_action_is_one_shot_and_replacement_is_independent(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    toast = Toast(host)
    calls = []
    toast.show_message("Removed", "Undo", lambda: calls.append("first"))
    toast.action_button.click()
    toast.action_button.click()
    toast._invoke_action()
    assert calls == ["first"]
    assert toast.isHidden()
    toast.show_message("Removed again", "Undo", lambda: calls.append("second"))
    toast.action_button.click()
    assert calls == ["first", "second"]


def test_toast_expiration_clears_action(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    toast = Toast(host)
    calls = []
    toast.show_message("Removed", "Undo", lambda: calls.append(True))
    toast._timer.timeout.emit()
    toast._invoke_action()
    assert not calls
