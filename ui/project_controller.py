from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from core import project as project_io
from core.exceptions import ProjectFileError
from core.project import ProjectState
from ui.app_identity import APP_TITLE
from ui.project_binding import apply_project_state, collect_project_state
from ui.recent_projects import add_recent_project, remove_recent_project

if TYPE_CHECKING:
    from ui.main_window import MainWindow

UNTITLED_PROJECT = "Untitled"
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class ProjectController:

    def __init__(
        self, host: "MainWindow", path: Optional[str] = None, name: Optional[str] = None
    ) -> None:
        self._host = host
        self.path: Optional[str] = path
        self.name: str = name or UNTITLED_PROJECT
        self._named_in_title = path is not None

    def apply_window_title(self) -> None:
        named = self._named_in_title and bool(self.name)
        self._host.setWindowTitle(f"{APP_TITLE} — {self.name}" if named else APP_TITLE)

    def current_state(self) -> ProjectState:
        session = self._host.session
        fallback = project_io.default_project_name(session.file_path, session.dxf_path)
        return collect_project_state(
            self._host.panel,
            name=self.name or fallback,
            txt_file_path=session.file_path,
            dxf_file_path=session.dxf_path,
            dxf_content=self._host.dxf_viewer.to_dxf_text(),
        )

    def load_state(self, state: ProjectState) -> None:
        self.name = state.name
        apply_project_state(self._host.panel, state)
        missing = self._host.documents.restore_project_files(state)
        if missing:
            self._host.flash_status(
                f"Could not find: {', '.join(missing)} (rest of the project was restored)", ms=5000
            )

    def save(self) -> None:
        if not self.path:
            self.save_as()
            return
        self._save_to(self.path, self.current_state())

    def save_as(self) -> None:
        state = self.current_state()
        suggested = state.name + project_io.PROJECT_FILE_EXTENSION
        path, _ = QFileDialog.getSaveFileName(
            self._host, "Save Project", suggested, project_io.PROJECT_FILE_FILTER
        )
        if not path:
            return
        if not path.lower().endswith(project_io.PROJECT_FILE_EXTENSION):
            path += project_io.PROJECT_FILE_EXTENSION
        state.name = os.path.splitext(os.path.basename(path))[0]
        self._save_to(path, state)

    def _save_to(self, path: str, state: ProjectState) -> None:
        try:
            project_io.save_project(path, state)
        except ProjectFileError as exc:
            self._host.flash_status(str(exc))
            return
        self._set_identity(state.name, path)
        add_recent_project(self._host.settings, path)
        self._host.flash_status(f"Saved project {os.path.basename(path)}")

    def rename(self) -> None:
        new_name = self._ask_new_name()
        if new_name is None:
            return
        path = self.path
        if path is not None:
            path = self._rename_file(path, new_name)
            if path is None:
                return
        self._set_identity(new_name, path)
        self._host.flash_status(f"Renamed to {new_name}")

    def _ask_new_name(self) -> Optional[str]:
        text, ok = QInputDialog.getText(
            self._host, "Rename Project", "Project name:", text=self.name
        )
        new_name = text.strip()
        if not ok or not new_name or new_name == self.name:
            return None
        if any(char in INVALID_FILENAME_CHARS for char in new_name):
            self._warn(f"A project name can't contain any of: {INVALID_FILENAME_CHARS}")
            return None
        return new_name

    def _rename_file(self, path: str, new_name: str) -> Optional[str]:
        new_path = os.path.join(
            os.path.dirname(path), new_name + project_io.PROJECT_FILE_EXTENSION
        )
        already_taken = os.path.exists(new_path) and os.path.normcase(
            new_path
        ) != os.path.normcase(path)
        if already_taken:
            self._warn(f'A project named "{new_name}" already exists in this folder.')
            return None
        try:
            os.replace(path, new_path)
        except OSError as exc:
            self._host.flash_status(f"Could not rename project file: {exc}")
            return None
        remove_recent_project(self._host.settings, path)
        add_recent_project(self._host.settings, new_path)
        return new_path

    def _set_identity(self, name: str, path: Optional[str]) -> None:
        self.name = name
        self.path = path
        self._named_in_title = True
        self.apply_window_title()

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self._host, "Rename Project", message)
