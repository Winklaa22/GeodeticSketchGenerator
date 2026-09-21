from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow

from core import project as project_io
from core.project import ProjectState
from ui.loading_overlay import LoadingOverlay, ProgressFn
from ui.recent_projects import add_recent_project


class WindowRouter:

    def __init__(self, owner: QMainWindow) -> None:
        self._owner = owner
        self._window: Optional[QMainWindow] = None
        self._loading = False

    def _swap(self, window: QMainWindow) -> None:
        self._window = window
        window.show()
        self._owner.close()

    def start_screen(self) -> None:
        from ui.start_screen import StartScreen

        self._swap(StartScreen())

    def editor(
        self,
        initial_state: Optional[ProjectState] = None,
        project_path: Optional[str] = None,
        progress: Optional[ProgressFn] = None,
    ) -> None:
        from ui.editor.window import MainWindow

        self._swap(
            MainWindow(initial_state=initial_state, project_path=project_path, progress=progress)
        )

    def open_path(self, settings: QSettings, path: str) -> None:
        if self._loading:
            return
        self._loading = True
        overlay = LoadingOverlay(self._owner)
        overlay.begin()
        try:
            overlay.report(5)
            state = project_io.open_any(path)
            overlay.report(15)
            project_path = project_io.project_path_if_saved(path)
            if project_path is not None:
                add_recent_project(settings, project_path)
            self.editor(initial_state=state, project_path=project_path, progress=overlay.report)
        finally:
            overlay.finish()
            self._loading = False
