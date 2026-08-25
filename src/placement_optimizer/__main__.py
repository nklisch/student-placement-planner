"""Desktop entry point: ``student-placement-planner`` or ``python -m placement_optimizer``."""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from contextlib import suppress
from importlib.resources import as_file, files
from pathlib import Path


def _write_self_test_report(message: str) -> None:
    report_path = os.environ.get("SPP_SELF_TEST_REPORT")
    if not report_path:
        return
    with suppress(OSError):
        Path(report_path).write_text(message, encoding="utf-8")


def _offline_builder_self_test() -> int:
    try:
        import osmium  # noqa: F401
        import valhalla

        from placement_optimizer.travel.regions import _valhalla_builder_environment

        suffix = ".exe" if sys.platform == "win32" else ""
        builder = Path(valhalla.__file__).resolve().parent / "bin" / f"valhalla_build_tiles{suffix}"
        result = subprocess.run(
            [str(builder), "--help"],
            env=_valhalla_builder_environment(builder),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        _write_self_test_report(traceback.format_exc())
        return 1
    if result.returncode != 0:
        _write_self_test_report(f"Offline builder exited with status {result.returncode}\n")
        return 1
    return 0


def _optimization_self_test() -> int:
    try:
        from ortools.sat.python import cp_model

        model = cp_model.CpModel()
        value = model.new_bool_var("runtime_check")
        model.add(value == 1)
        result = cp_model.CpSolver().solve(model)
    except Exception:
        _write_self_test_report(traceback.format_exc())
        return 1
    if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _write_self_test_report(f"Unexpected OR-Tools solve status: {result!r}\n")
        return 1
    return 0


def main() -> int:
    if "--self-test-offline-builder" in sys.argv:
        return _offline_builder_self_test()
    if "--self-test-optimization" in sys.argv:
        return _optimization_self_test()
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from placement_optimizer.ui.mainwindow import MainWindow
    from placement_optimizer.ui.theme import apply_theme, watch_color_scheme

    app = QApplication(sys.argv)
    app.setApplicationName("Student Placement Planner")
    app.setOrganizationName("StudentPlacementPlanner")
    app.setDesktopFileName("student-placement-planner")
    with as_file(files("placement_optimizer").joinpath("assets/app-icon.png")) as icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app)
    watch_color_scheme(app)

    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        project_path = str(Path(sys.argv[1]).resolve())
        QTimer.singleShot(0, lambda: window._open_path(project_path))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
