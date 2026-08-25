"""Shared fixtures for offscreen pytest-qt UI tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from placement_optimizer.application import LocationDraft, StudentDraft
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.mainwindow import MainWindow
from placement_optimizer.ui.sample_data import build_sample_session
from placement_optimizer.ui.theme import apply_theme


@pytest.fixture(scope="session", autouse=True)
def _apply_theme(qapp):
    apply_theme(qapp)
    return qapp


@pytest.fixture
def controller() -> SessionController:
    return SessionController()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch) -> MainWindow:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    main_window = MainWindow()
    # Tests routinely leave the draft modified; never block on the
    # unsaved-changes prompt (qtbot closes widgets before fixture teardown).
    main_window._confirm_close = lambda: "discard"
    qtbot.addWidget(main_window)
    return main_window


@pytest.fixture
def ready_window(window) -> MainWindow:
    """A main window with the complete sample project loaded."""

    window.controller.set_session(build_sample_session())
    return window


@pytest.fixture
def named_window(window) -> MainWindow:
    """A window whose roster uses the Aisha/Mateo/Ana sample names."""

    session = window.controller.session
    session.add_student(StudentDraft("student-a", "Aisha", "s1"))
    session.add_student(StudentDraft("student-b", "Mateo", "s2"))
    session.add_student(StudentDraft("student-c", "Ana", "s3"))
    session.add_location(LocationDraft("location-a", "North Clinic", "l1", "2"))
    session.add_location(LocationDraft("location-b", "Riverside", "l2", "2"))
    window.controller.notify()
    return window


def _fill_small_session(controller: SessionController) -> None:
    """Two students, two locations, and a complete manual grid."""

    session = controller.session
    student_one = session.add_student(StudentDraft("student-a", "Alice", "s1", "1 Main Street"))
    student_two = session.add_student(StudentDraft("student-b", "Bob", "s2"))
    location_one = session.add_location(LocationDraft("location-a", "Library", "l1", "1"))
    location_two = session.add_location(LocationDraft("location-b", "Workshop", "l2", "1"))
    session.set_manual_time(student_one.key, location_one.key, "5")
    session.set_manual_time(student_one.key, location_two.key, "10")
    session.set_manual_time(student_two.key, location_one.key, "8")
    session.set_manual_time(student_two.key, location_two.key, "x")
    controller.notify()


@pytest.fixture
def fill_small():
    return _fill_small_session
