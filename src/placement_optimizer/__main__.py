"""Desktop entry point: ``student-placement-planner`` or ``python -m placement_optimizer``."""

from __future__ import annotations

import subprocess
import sys
from importlib.resources import as_file, files
from pathlib import Path


def _offline_builder_self_test() -> int:
    try:
        import osmium  # noqa: F401
        import valhalla

        suffix = ".exe" if sys.platform == "win32" else ""
        builder = Path(valhalla.__file__).resolve().parent / "bin" / f"valhalla_build_tiles{suffix}"
        result = subprocess.run(
            [str(builder), "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (ImportError, OSError, subprocess.SubprocessError):
        return 1
    return 0 if result.returncode == 0 else 1


def main() -> int:
    if "--self-test-offline-builder" in sys.argv:
        return _offline_builder_self_test()
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
