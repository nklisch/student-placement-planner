"""Desktop entry point: ``placement-optimizer`` or ``python -m placement_optimizer``."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from placement_optimizer.ui.mainwindow import MainWindow
    from placement_optimizer.ui.theme import apply_theme, watch_color_scheme

    app = QApplication(sys.argv)
    app.setApplicationName("Student Placement Planner")
    app.setOrganizationName("StudentPlacementOptimizer")
    app.setDesktopFileName("student-placement-optimizer")
    apply_theme(app)
    watch_color_scheme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
