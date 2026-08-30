"""Project files, CSV import recovery, and unsaved-work behavior."""

from __future__ import annotations


def test_save_and_open_round_trip(ready_window, qtbot, tmp_path) -> None:
    window = ready_window
    target = tmp_path / "example.spp"

    assert window._save_to(str(target))
    assert target.exists()
    assert not window.controller.session.is_modified

    # Reopen into the same window; content and manual grid survive.
    window._open_path(str(target))
    session = window.controller.session
    assert session.name == "Sample project"
    assert len(session.students) == 8
    assert [row.name for row in session.locations] == [
        "Target Loveland",
        "Walmart Supercenter Loveland",
        "Whole Foods Market Fort Collins",
        "The Home Depot North Fort Collins",
    ]
    assert session.locations[0].address == "1725 Rocky Mountain Ave, Loveland, CO 80538"
    assert session.locations[2].address == "2201 S College Ave, Fort Collins, CO 80525"
    assert all(row.coordinates for row in (*session.students, *session.locations))
    assert not session.is_modified
    assert session.readiness().ready


def test_corrupt_project_offers_recovery(window, tmp_path, monkeypatch) -> None:
    broken = tmp_path / "broken.spp"
    broken.write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(window, "_ask_corrupt_project", lambda: "new")

    window._open_path(str(broken))

    session = window.controller.session
    assert session.students == []
    assert session.locations == []
    assert not session.is_modified


def test_incomplete_draft_save_preserves_every_raw_value(window, fill_small, tmp_path) -> None:
    fill_small(window.controller)
    session = window.controller.session
    session.update_location(0, capacity="")
    session.set_manual_time(session.students[0].key, session.locations[1].key, "many")

    target = tmp_path / "incomplete.spp"
    assert window._save_to(str(target))

    window._open_path(str(target))
    restored = window.controller.session
    assert len(restored.students) == 2
    assert len(restored.locations) == 2
    assert restored.locations[0].capacity == ""
    assert (
        restored.manual_times[
            restored.students[0].key,
            restored.locations[1].key,
        ]
        == "many"
    )


def test_import_csv_retains_invalid_raw_rows(window, qtbot, tmp_path) -> None:
    csv_file = tmp_path / "students.csv"
    csv_file.write_text(
        "student_id,name,address,latitude,longitude\n"
        "s1,Alice,1 Main Street,51.5,-0.12\n"
        "s2,Bob,2 High Street,not-a-number,-1.2\n",
        encoding="utf-8",
    )
    reports = []
    window.report_import = lambda **kwargs: reports.append(kwargs)

    students = window.pages[0]
    students.import_csv_path(str(csv_file))
    qtbot.waitUntil(lambda: students._import_worker is None, timeout=5000)

    session = window.controller.session
    assert len(session.students) == 2
    # The invalid row keeps its original text and is marked for repair.
    bob = next(row for row in session.students if row.id == "s2")
    assert "not-a-number" in bob.coordinates
    issues = session.readiness().issues
    assert any(issue.row_key == bob.key for issue in issues)
    assert reports and reports[0]["kept"] == 1

    # Discard import routes through one undo step.
    reports[0]["on_discard"]()
    assert session.students == []


def test_import_discard_restores_prior_rows(window, qtbot, tmp_path) -> None:
    students = window.pages[0]
    students.model.paste_block(0, 0, "Existing\ts0")
    csv_file = tmp_path / "more.csv"
    csv_file.write_text("student_id,name\ns9,New\n", encoding="utf-8")
    window.report_import = lambda **kwargs: None

    students.import_csv_path(str(csv_file))
    qtbot.waitUntil(lambda: students._import_worker is None, timeout=5000)
    assert len(window.controller.session.students) == 2

    students.model.undo.undo()
    remaining = window.controller.session.students
    assert len(remaining) == 1
    assert remaining[0].name == "Existing"


def test_csv_read_and_parse_run_off_ui_thread(window, qtbot, tmp_path, monkeypatch) -> None:
    import threading

    from placement_optimizer.projects import parse_students_csv

    csv_file = tmp_path / "students.csv"
    csv_file.write_text("student_id,name\ns1,Alice\n", encoding="utf-8")
    main_thread = threading.get_ident()
    parse_threads: list[int] = []
    students = window.pages[0]

    def recording_parser(text):
        parse_threads.append(threading.get_ident())
        return parse_students_csv(text)

    monkeypatch.setattr(students, "_parse", recording_parser)
    students.import_csv_path(str(csv_file))
    qtbot.waitUntil(lambda: students._import_worker is None, timeout=5000)

    assert parse_threads
    assert parse_threads[0] != main_thread
    assert window.controller.session.students[0].name == "Alice"


def test_close_waits_for_active_import_worker(window, qtbot, tmp_path, monkeypatch) -> None:
    import threading

    from placement_optimizer.projects import parse_students_csv

    csv_file = tmp_path / "students.csv"
    csv_file.write_text("student_id,name\ns1,Alice\n", encoding="utf-8")
    started = threading.Event()
    release = threading.Event()
    students = window.pages[0]

    def slow_parser(text):
        started.set()
        release.wait(2)
        return parse_students_csv(text)

    monkeypatch.setattr(students, "_parse", slow_parser)
    window.show()
    students.import_csv_path(str(csv_file))
    assert started.wait(2)

    window.close()
    assert window._close_after_background
    assert window.isVisible()
    release.set()

    qtbot.waitUntil(lambda: students._import_worker is None, timeout=5000)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)
    assert window.controller.session.students == []


def test_unsaved_close_guard(window, fill_small, monkeypatch) -> None:
    assert window.maybe_close()  # unmodified: closes freely

    fill_small(window.controller)
    monkeypatch.setattr(window, "_confirm_close", lambda: "cancel")
    assert not window.maybe_close()
    monkeypatch.setattr(window, "_confirm_close", lambda: "discard")
    assert window.maybe_close()


def test_window_title_and_modified_indicator(window, fill_small) -> None:
    assert not window.isWindowModified()
    fill_small(window.controller)
    assert window.isWindowModified()
    assert "Untitled placement" in window.windowTitle()
