"""Provider placeholder isolation: offline/online cards are honest, inert panels."""

from __future__ import annotations

import inspect

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QLabel

from placement_optimizer.application import TravelMode
from placement_optimizer.ui.pages import travel as travel_module


def test_offline_card_shows_setup_placeholder_without_actions(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.offline_card.select()

    session = window.controller.session
    assert session.travel_mode is TravelMode.OFFLINE
    assert page.panels.currentIndex() == 1

    buttons = page.panels.currentWidget().findChildren(QAbstractButton)
    assert not [button for button in buttons if button.isEnabled()]
    # No fake calculation: the mode cannot become ready in Phase D.
    readiness = session.readiness()
    assert not readiness.travel_ready


def test_online_card_shows_disclosure_and_no_fake_actions(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.online_card.select()

    session = window.controller.session
    assert session.travel_mode is TravelMode.GOOGLE
    assert page.panels.currentIndex() == 2

    panel = page.panels.currentWidget()
    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert any("never leave this computer" in text for text in texts)
    buttons = panel.findChildren(QAbstractButton)
    assert not [button for button in buttons if button.isEnabled()]
    assert not session.readiness().travel_ready


def test_mode_radios_stay_exclusive(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]

    page.manual_card.select()
    page.manual_card.radio.click()

    assert page.manual_card.radio.isChecked()
    assert (
        sum(
            card.radio.isChecked()
            for card in (page.manual_card, page.offline_card, page.online_card)
        )
        == 1
    )
    assert window.controller.session.travel_mode is TravelMode.MANUAL


def test_clicking_mode_card_body_selects_it(window, qtbot, fill_small) -> None:
    fill_small(window.controller)
    window.show()
    window.navigate(3)
    page = window.pages[3]

    qtbot.mouseClick(page.offline_card, Qt.MouseButton.LeftButton)

    assert page.offline_card.radio.isChecked()
    assert window.controller.session.travel_mode is TravelMode.OFFLINE


def test_travel_page_imports_no_provider_or_network_code() -> None:
    source = inspect.getsource(travel_module)
    for forbidden in ("httpx", "travel.google", "travel.local", "build_travel_matrix", "Geocoder"):
        assert forbidden not in source


def test_manual_mode_remains_the_ready_path(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.manual_card.select()

    readiness = window.controller.session.readiness()
    assert readiness.travel_ready
    assert "Travel times ready" in page.status_label.text()
