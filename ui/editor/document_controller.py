from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable, List

from PyQt6.QtWidgets import QFileDialog

from core.project import ProjectState
from ui.widgets import DxfSourceRow

if TYPE_CHECKING:
    from ui.editor.window import MainWindow

UNTITLED_DRAWING = "Untitled drawing"
DEFAULT_DXF_NAME = "drawing.dxf"


def _load_first_match(paths: List[str], suffix: str, loader: Callable[[str], None]) -> None:
    matches = [path for path in paths if path.lower().endswith(suffix)]
    if matches:
        loader(matches[0])


class DocumentController:

    def __init__(self, host: "MainWindow") -> None:
        self._host = host

    @property
    def _source_row(self) -> DxfSourceRow:
        return self._host.left_column.dxf_source_row

    def select_point_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._host, "Open TXT File", "", "Text Files (*.txt)"
        )
        if path:
            self.load_point_file(path)

    def on_point_files_dropped(self, paths: List[str]) -> None:
        _load_first_match(paths, ".txt", self.load_point_file)

    def load_point_file(self, file_path: str) -> None:
        delimiter_mode = self._host.panel.delimiter_tab.delimiter_mode
        self._host.session.load_points(file_path, delimiter_mode)
        self._host.refresh()

    def select_dxf_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self._host, "Open DXF File", "", "DXF Files (*.dxf)")
        if path:
            self.load_dxf_file(path)

    def on_dxf_files_dropped(self, paths: List[str]) -> None:
        _load_first_match(paths, ".dxf", self.load_dxf_file)

    def load_dxf_file(self, file_path: str) -> None:
        ok, message = self._host.dxf_viewer.load_file(file_path)
        self._after_dxf_load(ok, message, file_path)

    def load_dxf_from_text(self, content: str, file_path: str) -> None:
        ok, message = self._host.dxf_viewer.load_from_text(content)
        self._after_dxf_load(ok, message, file_path)

    def _after_dxf_load(self, ok: bool, message: str, file_path: str) -> None:
        if not ok:
            self._source_row.show_error(message)
            return
        self._host.session.set_dxf_path(file_path)
        self.refresh_dxf_source()
        self._host.refresh()

    def refresh_dxf_source(self) -> None:
        dxf_path = self._host.session.dxf_path
        name = os.path.basename(dxf_path) if dxf_path else UNTITLED_DRAWING
        self._source_row.set_file(name, self._host.dxf_viewer.entity_count)

    def clear_dxf_file(self) -> None:
        self._host.session.set_dxf_path("")
        self._host.dxf_viewer.clear()
        self._source_row.set_empty()
        self._host.refresh()

    def save_dxf(self) -> None:
        viewer = self._host.dxf_viewer
        if not viewer.has_document:
            return
        session = self._host.session
        suggested = os.path.basename(session.dxf_path) if session.dxf_path else DEFAULT_DXF_NAME
        path, _ = QFileDialog.getSaveFileName(self._host, "Save DXF", suggested, "DXF Files (*.dxf)")
        if not path:
            return
        viewer.save_document(path)
        session.dxf_path = path
        self.refresh_dxf_source()
        self._host.flash_status(f"Saved to {os.path.basename(path)}")

    def restore_project_files(self, state: ProjectState) -> List[str]:
        missing: List[str] = []
        if state.txt_file_path:
            self._restore_or_report(state.txt_file_path, self.load_point_file, missing)
        if state.dxf_content:
            self.load_dxf_from_text(state.dxf_content, state.dxf_file_path)
        elif state.dxf_file_path:
            self._restore_or_report(state.dxf_file_path, self.load_dxf_file, missing)
        return missing

    @staticmethod
    def _restore_or_report(
        path: str, loader: Callable[[str], None], missing: List[str]
    ) -> None:
        if os.path.exists(path):
            loader(path)
        else:
            missing.append(os.path.basename(path))
