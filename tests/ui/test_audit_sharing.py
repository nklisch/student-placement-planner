"""Sharing must distinguish old assignments and failed calculations."""

from placement_optimizer.application import solve_project


def show_result(window):
    session = window.controller.session
    project = session.build_project().project
    outcome = solve_project(project)
    session.mark_result()
    window.pages[4].show_outcome(outcome, project)
    window.refresh_chrome()
    return outcome


def test_stale_export_requires_explicit_confirmation(ready_window, monkeypatch, tmp_path):
    show_result(ready_window)
    session = ready_window.controller.session
    session.update_location(0, capacity="0")
    ready_window.controller.notify()
    prompts = []
    monkeypatch.setattr(
        ready_window, "_confirm_previous_result", lambda verb: prompts.append(verb) or False
    )
    target = tmp_path / "placements.csv"
    monkeypatch.setattr(ready_window, "ask_save_csv", lambda *args: str(target))
    ready_window.export_results()
    assert prompts == ["Export"]
    assert not target.exists()
    monkeypatch.setattr(ready_window, "_confirm_previous_result", lambda _verb: True)
    ready_window.export_results()
    assert target.exists()
    assert "student_id" in target.read_text()


def test_stale_print_marks_the_preview(ready_window, monkeypatch):
    from placement_optimizer.ui import printing

    show_result(ready_window)
    ready_window.controller.session.update_location(0, capacity="0")
    ready_window.controller.notify()
    monkeypatch.setattr(ready_window, "_confirm_previous_result", lambda _verb: True)
    flags = []

    class Preview:
        def __init__(self, *args, previous_result=False):
            flags.append(previous_result)

        def exec(self):
            return 0

    monkeypatch.setattr(printing, "ResultsPrintPreviewDialog", Preview)
    ready_window.print_results()
    assert flags == [True]


def test_infeasible_result_does_not_mark_results_ready(ready_window):
    session = ready_window.controller.session
    for index in range(len(session.locations)):
        session.update_location(index, capacity="0")
    outcome = show_result(ready_window)
    assert not outcome.result.placements
    assert not ready_window.export_action.isEnabled()
    assert not ready_window.print_action.isEnabled()
    assert ready_window.steps_model._statuses[4] == "!"
