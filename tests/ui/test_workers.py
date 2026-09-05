from __future__ import annotations

import asyncio

from placement_optimizer.ui.workers import AsyncOperationWorker


def test_async_operation_worker_preserves_large_download_counts() -> None:
    async def operation(_worker):
        return None

    worker = AsyncOperationWorker(operation)
    progress = []
    worker.progress.connect(lambda completed, total, message: progress.append((completed, total)))

    worker.report_progress(3 * 1024**3, 5 * 1024**3, "Downloading…")

    assert progress == [(3 * 1024**3, 5 * 1024**3)]


def test_async_operation_worker_cancels_active_network_style_task(qtbot) -> None:
    started = False
    cancelled = []

    async def operation(_worker):
        nonlocal started
        started = True
        await asyncio.Event().wait()

    worker = AsyncOperationWorker(operation)
    worker.cancelled_operation.connect(lambda: cancelled.append(True))
    worker.start()
    qtbot.waitUntil(lambda: started, timeout=2000)

    worker.cancel()

    qtbot.waitUntil(lambda: bool(cancelled) and not worker.isRunning(), timeout=2000)
    assert cancelled == [True]
    worker.deleteLater()


def test_solve_worker_converts_unexpected_exception_to_recoverable_outcome(monkeypatch) -> None:
    from placement_optimizer.application import OutcomeKind, PlacementProject
    from placement_optimizer.ui import workers

    def fail(*args):
        raise RuntimeError("secret engine payload")

    monkeypatch.setattr(workers, "solve_project", fail)
    worker = workers.SolveWorker(PlacementProject())
    outcomes = []
    worker.finished_outcome.connect(outcomes.append)
    worker.run()
    assert len(outcomes) == 1
    assert outcomes[0].kind is OutcomeKind.UNAVAILABLE
    assert "inputs were kept" in outcomes[0].message
    assert "secret" not in outcomes[0].message


def test_async_worker_covers_factory_failure_without_leaking_exception() -> None:
    def fail(worker):
        raise RuntimeError("secret-key")

    worker = AsyncOperationWorker(fail)
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert len(failures) == 1
    assert "Try again" in failures[0]
    assert "secret" not in failures[0]


def test_csv_worker_recovers_from_parser_failure(tmp_path) -> None:
    from placement_optimizer.ui.workers import CsvImportWorker

    path = tmp_path / "input.csv"
    path.write_text("name\nAlice", encoding="utf-8")

    def fail(text):
        raise ValueError("bad parser input")

    worker = CsvImportWorker(str(path), fail)
    failures = []
    worker.failed.connect(lambda: failures.append(True))
    worker.run()
    assert failures == [True]
