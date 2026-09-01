from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core import project as project_io
from core.commands.base import Command
from core.commands.composite import CompositeCommand
from core.exceptions import AppError, ProjectFileError
from core.project import ProjectState
from core.session import AppState, EditorSession
from core.sheets import SheetSet
from core.survey_draw_service import SurveyDrawService
from core.validation import ensure_draw_modes, ensure_has_data, ensure_selection
from ui.app_identity import app_settings
from ui.dxf.viewer import DxfViewer
from ui.editor.document_controller import DocumentController
from ui.editor.layout_controller import LayoutController
from ui.editor.layout_panel import LayoutPanel
from ui.editor.left_column import LeftColumn
from ui.editor.menu_bar import MenuBar
from ui.editor.preview_panel import PreviewPanel
from ui.editor.project_controller import ProjectController
from ui.editor.sections_panel import SectionsPanel
from ui.editor.status_bar import StatusBar
from ui.theme import LEFT_COLUMN_WIDTH, SPACE_LG, SPACE_XL
from ui.theme.assets import ICON_PATH
from ui.theme.style import APP_STYLESHEET
from ui.window_router import WindowRouter

LEFT_COLUMN_WIDTH_KEY = "ui/leftColumnWidth"


class MainWindow(QMainWindow):

    def __init__(
        self, initial_state: Optional[ProjectState] = None, project_path: Optional[str] = None
    ) -> None:
        super().__init__()
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.settings = app_settings()

        self.session = EditorSession()
        self.sheets = SheetSet()
        self.survey_draw_service = SurveyDrawService()
        self.router = WindowRouter(self)
        self.documents = DocumentController(self)
        self.project = ProjectController(
            self,
            path=project_path,
            name=initial_state.name if initial_state is not None else None,
        )

        self._build_ui()
        self.layouts = LayoutController(self)
        self._wire_signals()
        self.setStyleSheet(APP_STYLESHEET)
        if initial_state is not None:
            self.project.load_state(initial_state)
        self.project.apply_window_title()
        self.refresh()

    def _build_ui(self) -> None:
        self.dxf_viewer = DxfViewer()
        self.panel = SectionsPanel(self.settings)
        self.layout_panel = LayoutPanel()
        self.left_column = LeftColumn(
            [
                ("point_file", "Point File", self.panel),
                ("layers", "Layers", self.dxf_viewer.layer_panel),
                ("layout", "Layout", self.layout_panel),
            ]
        )
        self.preview_panel = PreviewPanel(self.dxf_viewer)
        self.status_bar = StatusBar()
        self.menu_bar = MenuBar(self.settings)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.menu_bar)
        root.addWidget(self._build_content(), 1)
        root.addWidget(self.status_bar)

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(SPACE_LG)
        self.main_splitter.addWidget(self.left_column)
        self.main_splitter.addWidget(self.preview_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        saved_width = self.settings.value(LEFT_COLUMN_WIDTH_KEY, LEFT_COLUMN_WIDTH, type=int)
        self.main_splitter.setSizes([saved_width, max(1, 1000 - saved_width)])
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(self.main_splitter)
        return content

    def _wire_signals(self) -> None:
        self.menu_bar.newProjectRequested.connect(self.new_project)
        self.menu_bar.openProjectRequested.connect(self.open_project_dialog)
        self.menu_bar.recentProjectRequested.connect(self._open_path)
        self.menu_bar.saveProjectRequested.connect(self.project.save)
        self.menu_bar.saveProjectAsRequested.connect(self.project.save_as)
        self.menu_bar.renameProjectRequested.connect(self.project.rename)
        self.menu_bar.exportDxfRequested.connect(self.documents.save_dxf)
        self.menu_bar.closeProjectRequested.connect(self.open_start_screen)
        self.menu_bar.undoRequested.connect(lambda: self.dxf_viewer.echo(self.dxf_viewer.undo()))
        self.menu_bar.redoRequested.connect(lambda: self.dxf_viewer.echo(self.dxf_viewer.redo()))
        self.menu_bar.editMenuAboutToShow.connect(self._sync_edit_menu)

        self.panel.option_changed.connect(self._on_config_changed)
        self.panel.layers_changed.connect(self._on_config_changed)
        self.panel.delimiter_changed.connect(self._on_delimiter_changed)
        self.panel.file_requested.connect(self.documents.select_point_file)
        self.panel.files_dropped.connect(self.documents.on_point_files_dropped)

        source_row = self.left_column.dxf_source_row
        source_row.fileRequested.connect(self.documents.select_dxf_file)
        source_row.filesDropped.connect(self.documents.on_dxf_files_dropped)
        source_row.clearRequested.connect(self.documents.clear_dxf_file)

        self.preview_panel.saveRequested.connect(self.documents.save_dxf)
        self.preview_panel.applyRequested.connect(self.apply_to_dxf)

        self.dxf_viewer.documentChanged.connect(self.refresh)
        self.layouts.wire()

    def _sync_edit_menu(self) -> None:
        self.menu_bar.set_undo_redo_enabled(self.dxf_viewer.can_undo(), self.dxf_viewer.can_redo())

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self.settings.setValue(LEFT_COLUMN_WIDTH_KEY, self.main_splitter.sizes()[0])

    def _on_config_changed(self, *_args) -> None:
        self.session.invalidate()
        self.refresh()

    def _on_delimiter_changed(self) -> None:
        if self.session.has_file:
            self.session.reparse_points(self.panel.delimiter_tab.delimiter_mode)
        self._on_config_changed()

    def refresh(self) -> None:
        state = self.session.state
        self.panel.update_visibility(state is not AppState.EMPTY)
        self._refresh_point_file_view(state)
        self._refresh_status_bar(state)
        self._refresh_preview(state)
        self.panel.refresh_modified_dots()
        self.layouts.refresh()

    def _refresh_point_file_view(self, state: AppState) -> None:
        if state is AppState.EMPTY:
            self.panel.show_drop_zone()
        else:
            self.panel.show_file(
                self.session.file_name, self.session.point_count, self.session.file_size_text
            )

    def _refresh_status_bar(self, state: AppState) -> None:
        self.status_bar.update_state(
            state,
            file_text=f"{self.session.file_name} · {self.session.point_count} points",
            layer_name=self.panel.layer_tab.default_layer_name(),
            delimiter_name=self.panel.delimiter_tab.display_name,
        )

    def _refresh_preview(self, state: AppState) -> None:
        has_document = self.dxf_viewer.has_document
        if has_document:
            self.preview_panel.set_meta(self.dxf_viewer.entity_count, self.dxf_viewer.layer_count)
        else:
            self.preview_panel.clear_meta()

        if state is AppState.ERROR:
            self.preview_panel.show_error(self.session.last_error)
        else:
            self.preview_panel.clear_error()

        self.preview_panel.set_actions_enabled(
            save=has_document, apply=state is not AppState.EMPTY
        )

    def flash_status(self, message: str, ms: int = 2500) -> None:
        self.status_bar.flash(message)
        QTimer.singleShot(ms, self.refresh)

    def _build_draw_command(self) -> Command:
        ensure_has_data(self.session.data, self.session.file_path)
        selected_numbers = self.panel.selection_tab.get_selected_numbers(self.session.data)
        ensure_selection(selected_numbers)
        draw_modes = self.panel.draw_tab.draw_modes
        ensure_draw_modes(draw_modes)
        commands = [
            self.survey_draw_service.build_command(
                self.session.data, selected_numbers, self.panel.build_generation_config(mode)
            )
            for mode in draw_modes
        ]
        return commands[0] if len(commands) == 1 else CompositeCommand(commands)

    def apply_to_dxf(self) -> None:
        self.panel.layer_tab.persist(self.settings)
        try:
            command = self._build_draw_command()
        except AppError as exc:
            self.session.fail(str(exc))
            self.refresh()
            return
        self.session.last_error = None
        try:
            self.dxf_viewer.execute_command(command)
        except Exception as exc:
            self.session.fail(f"Could not draw into the DXF file: {exc}")
            self.refresh()
            return
        self.session.mark_applied()
        self.documents.refresh_dxf_source()
        self.refresh()

    def open_start_screen(self) -> None:
        self.router.start_screen()

    def new_project(self) -> None:
        self.router.editor()

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open",
            "",
            f"{project_io.PROJECT_FILE_FILTER};;DXF Files (*.dxf);;Text Files (*.txt)",
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            self.router.open_path(self.settings, path)
        except ProjectFileError as exc:
            self.flash_status(str(exc))
