"""PySide6 desktop interface.

The UI consumes the parent-authored application interfaces (DraftSession,
solve_project, project files, CSV import/export) and never formulates
optimization or provider requests itself.
"""

from placement_optimizer.ui.mainwindow import MainWindow

__all__ = ["MainWindow"]
