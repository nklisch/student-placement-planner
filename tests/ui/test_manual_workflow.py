"""The full manual workflow: typed/pasted rows, manual times, solve, export."""

from __future__ import annotations

from PySide6.QtCore import Qt

from placement_optimizer.application import DraftSession, OutcomeKind, SolveProjectOutcome

EDIT = Qt.ItemDataRole.EditRole


def _drive_workflow(window, qtbot) -> None:
    """Enter a complete problem through the actual grids and run it."""

    students = window.pages[0]
    window.navigate(0)
    students.model.paste_block(
        0, 0, "Alice\ts1\t1 Main Street\nBob\ts2\t2 High Street\nCara\ts3\t9 Hill Road"
    )

    locations = window.pages[1]
    window.navigate(1)
    locations.model.paste_block(0, 0, "Library\tl1\t2\nWorkshop\tl2\t1")

    travel = window.pages[2 + 1]
    window.navigate(3)
    travel.model.paste_block(0, 0, "5\t10\n8\tx\n12\t7")

    readiness = window.controller.session.readiness()
    assert readiness.ready, readiness.issues

    window.find_placements()
    qtbot.waitUntil(lambda: window.pages[4].outcome is not None, timeout=10000)
    qtbot.waitUntil(lambda: window._worker is None, timeout=10000)


def test_manual_workflow_end_to_end(window, qtbot) -> None:
    _drive_workflow(window, qtbot)

    results = window.pages[4]
    assert window.stack.currentIndex() == 4
    assert results.outcome.kind is OutcomeKind.SUCCESS
    assert results.banner.title.text() == "Placements found — every rule is satisfied."
    assert results.stat_longest.value_label.text() != "—"

    model = results.student_table.model()
    names = [model.index(row, 0).data() for row in range(model.rowCount())]
    assert sorted(names) == ["Alice", "Bob", "Cara"]
    placements = [model.index(row, 1).data() for row in range(model.rowCount())]
    assert all(place in {"Library", "Workshop"} for place in placements)


def test_results_become_stale_and_update_after_an_edit(window, qtbot) -> None:
    _drive_workflow(window, qtbot)
    session = window.controller.session

    window.navigate(3)
    travel = window.pages[3]
    travel.model.setData(travel.model.index(0, 0), "6", EDIT)

    assert session.results_are_stale
    assert window.run_button.text() == "Update placements"
    results = window.pages[4]
    assert results.banner.title.text() == "These placements predate your latest changes."
    # Prior results stay visible under the stale banner.
    assert results.student_table.model().rowCount() == 3

    window.find_placements()
    qtbot.waitUntil(lambda: not session.results_are_stale, timeout=10000)
    assert results.banner.title.text() == "Placements found — every rule is satisfied."


def test_export_results_writes_csv(window, qtbot, tmp_path, monkeypatch) -> None:
    _drive_workflow(window, qtbot)
    target = tmp_path / "placements.csv"
    monkeypatch.setattr(window, "ask_save_csv", lambda *_args: str(target))

    window.export_results()

    text = target.read_text(encoding="utf-8")
    assert "student_name" in text
    assert "Alice" in text
    assert "Workshop" in text or "Library" in text


def test_solver_worker_cancellation_restores_previous_state(window, qtbot, monkeypatch) -> None:
    _drive_workflow(window, qtbot)
    previous = window.pages[4].outcome

    # Make the next solve slow enough to cancel deterministically.
    import placement_optimizer.ui.workers as workers

    def slow_solve(_project, cancellation):
        import time

        while not cancellation.is_cancelled:
            time.sleep(0.01)
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "The calculation was cancelled.")

    monkeypatch.setattr(workers, "solve_project", slow_solve)

    window.find_placements()
    qtbot.waitUntil(lambda: window._worker is not None, timeout=5000)
    qtbot.waitUntil(lambda: not window.solve_progress.isHidden(), timeout=5000)
    window.cancel_solve()

    assert not window.solve_progress.isHidden()
    assert window.solve_progress_label.text() == "Cancelling…"
    # The previous result is preserved after the worker exits safely.
    qtbot.waitUntil(lambda: window._worker is None, timeout=10000)
    assert window.solve_progress.isHidden()
    assert window.pages[4].outcome is previous


def test_first_run_cancellation_leaves_persistent_result_status(
    window, qtbot, fill_small, monkeypatch
) -> None:
    fill_small(window.controller)

    import threading
    import time

    import placement_optimizer.ui.workers as workers

    started = threading.Event()

    def controlled_solve(_project, cancellation):
        started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.01)
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "The calculation was cancelled.")

    monkeypatch.setattr(workers, "solve_project", controlled_solve)
    window.find_placements()
    assert started.wait(2)
    window.cancel_solve()

    qtbot.waitUntil(lambda: window._worker is None, timeout=5000)
    assert window.pages[4].outcome.kind is OutcomeKind.CANCELLED
    assert window.pages[4].banner.title.text() == "Cancelled."


def test_result_from_edited_in_flight_solve_is_marked_stale(window, qtbot, monkeypatch) -> None:
    _drive_workflow(window, qtbot)
    session = window.controller.session
    completed_outcome = window.pages[4].outcome

    import threading

    import placement_optimizer.ui.workers as workers

    started = threading.Event()
    release = threading.Event()

    def controlled_solve(_project, cancellation):
        started.set()
        while not release.wait(0.01):
            if cancellation.is_cancelled:
                return SolveProjectOutcome(OutcomeKind.CANCELLED, "Cancelled.")
        return completed_outcome

    monkeypatch.setattr(workers, "solve_project", controlled_solve)
    window.find_placements()
    assert started.wait(2)

    travel = window.pages[3]
    travel.model.setData(travel.model.index(0, 0), "6", EDIT)
    release.set()

    qtbot.waitUntil(lambda: window._worker is None, timeout=5000)
    assert session.results_are_stale
    assert window.pages[4].banner.title.text() == "These placements predate your latest changes."


def test_replacing_session_cancels_and_discards_in_flight_result(
    window, qtbot, monkeypatch
) -> None:
    _drive_workflow(window, qtbot)

    import threading
    import time

    import placement_optimizer.ui.workers as workers

    started = threading.Event()

    def controlled_solve(_project, cancellation):
        started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.01)
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "Cancelled.")

    monkeypatch.setattr(workers, "solve_project", controlled_solve)
    window.find_placements()
    assert started.wait(2)

    replacement = DraftSession()
    window.controller.set_session(replacement)

    qtbot.waitUntil(lambda: window._worker is None, timeout=5000)
    assert window.controller.session is replacement
    assert window.pages[4].outcome is None


def test_close_waits_for_active_worker_to_exit(window, qtbot, monkeypatch) -> None:
    _drive_workflow(window, qtbot)

    import threading
    import time

    import placement_optimizer.ui.workers as workers

    started = threading.Event()

    def controlled_solve(_project, cancellation):
        started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.01)
        return SolveProjectOutcome(OutcomeKind.CANCELLED, "Cancelled.")

    monkeypatch.setattr(workers, "solve_project", controlled_solve)
    window.show()
    window.find_placements()
    assert started.wait(2)

    window.close()
    assert window._worker is not None
    assert window._close_after_worker

    qtbot.waitUntil(lambda: window._worker is None, timeout=5000)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)


def test_add_and_delete_row_shortcuts_route_to_the_current_page(window, qtbot) -> None:
    window.navigate(0)
    students = window.pages[0]
    students.model.paste_block(0, 0, "Alice\ts1\nBob\ts2")

    students.table.selectAll()
    window.edit_delete_rows()
    assert window.controller.session.students == []

    students.model.undo.undo()
    assert len(window.controller.session.students) == 2
