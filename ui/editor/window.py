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
from core.commands.text import ApplyFontToAllTextCommand
from core.exceptions import AppError, ProjectFileError
from core.project import ProjectState
from core.session import AppState, EditorSession
from core.sheets import SheetSet
from core.survey_draw_service import SurveyDrawService
from core.table_template import default_template
from core.validation import ensure_draw_modes, ensure_has_data, ensure_selection
from ui.app_identity import app_settings
from ui.dxf.viewer import DxfViewer
from ui.editor.document_controller import DocumentController
from ui.editor.fonts_panel import FontsPanel
from ui.editor.layout_controller import LayoutController
from ui.editor.layout_panel import LayoutPanel
from ui.editor.left_column import LeftColumn
from ui.editor.menu_bar import MenuBar
from ui.editor.preview_panel import PreviewPanel
from ui.editor.project_controller import ProjectController
from ui.editor.sections_panel import SectionsPanel
from ui.editor.status_bar import StatusBar
from ui.editor.table_template_controller import TableTemplateController
from ui.global_settings import new_project_table_template
from ui.i18n import tr
from ui.settings_dialog import SettingsDialog
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
        self._reapplying_layout = False
        self.table_template = (
            new_project_table_template(self.settings) if initial_state is None else default_template()
        )
        self.survey_draw_service = SurveyDrawService()
        self.router = WindowRouter(self)
        self.documents = DocumentController(self)
        self.project = ProjectController(
            self,
            path=project_path,
            name=initial_state.name if initial_state is not None else None,
        )
        self.table_template_controller = TableTemplateController(self)

        self._build_ui()
        self.layouts = LayoutController(self)
        self._wire_signals()
        self.refresh_table_template_bindings()
        self.setStyleSheet(APP_STYLESHEET)
        if initial_state is not None:
            self.project.load_state(initial_state)
        self.project.apply_window_title()
        self.refresh()

    def _build_ui(self) -> None:
        self.dxf_viewer = DxfViewer()
        self.panel = SectionsPanel(self.settings)
        self.layout_panel = LayoutPanel()
        self.fonts_panel = FontsPanel(self.settings)
        self.left_column = LeftColumn(
            [
                ("point_file", tr("sections.point_file"), self.panel),
                ("layers", tr("window.tab_layers"), self.dxf_viewer.layer_panel),
                ("layout", tr("window.tab_layout"), self.layout_panel),
                ("fonts", tr("window.tab_fonts"), self.fonts_panel),
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
        self.menu_bar.tableStructureRequested.connect(self.table_template_controller.open_editor)
        self.menu_bar.importTableTemplateRequested.connect(self.table_template_controller.import_template)
        self.menu_bar.exportTableTemplateRequested.connect(self.table_template_controller.export_template)
        self.menu_bar.closeProjectRequested.connect(self.open_start_screen)
        self.menu_bar.settingsRequested.connect(self.open_settings)
        self.menu_bar.undoRequested.connect(lambda: self.dxf_viewer.echo(self.dxf_viewer.undo()))
        self.menu_bar.redoRequested.connect(lambda: self.dxf_viewer.echo(self.dxf_viewer.redo()))
        self.menu_bar.editMenuAboutToShow.connect(self._sync_edit_menu)

        self.panel.option_changed.connect(self._on_config_changed)
        self.panel.layers_changed.connect(self._on_config_changed)
        self.panel.delimiter_changed.connect(self._on_delimiter_changed)
        self.panel.file_requested.connect(self.documents.select_point_file)
        self.panel.files_dropped.connect(self.documents.on_point_files_dropped)
        self.fonts_panel.optionsChanged.connect(self._on_config_changed)
        self.fonts_panel.applyToAllRequested.connect(self._on_apply_font_to_all)

        source_row = self.left_column.dxf_source_row
        source_row.fileRequested.connect(self.documents.select_dxf_file)
        source_row.filesDropped.connect(self.documents.on_dxf_files_dropped)
        source_row.clearRequested.connect(self.documents.clear_dxf_file)

        self.preview_panel.saveRequested.connect(self.documents.save_dxf)
        self.preview_panel.applyRequested.connect(self.apply_to_dxf)

        self.dxf_viewer.documentChanged.connect(self._on_document_changed)
        self.layouts.wire()

    def _sync_edit_menu(self) -> None:
        self.menu_bar.set_undo_redo_enabled(self.dxf_viewer.can_undo(), self.dxf_viewer.can_redo())

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self.settings.setValue(LEFT_COLUMN_WIDTH_KEY, self.main_splitter.sizes()[0])

    def _on_config_changed(self, *_args) -> None:
        self.session.invalidate()
        self.refresh()

    def _on_document_changed(self) -> None:
        # The active sheet's resolved scale/frame (e.g. "fit to content") depends
        # on the document's extents, so any edit that changes those extents -
        # running a draw command, undo/redo, loading a file - can leave the sheet
        # showing a stale frame that no longer matches what actually gets
        # exported (which always resolves fresh at export time). Re-resolving it
        # here keeps the preview in sync; the reentrancy guard is needed because
        # that re-resolve itself re-renders the viewer, which re-emits this same
        # signal - without it this would recurse forever.
        self.refresh()
        if self._reapplying_layout:
            return
        self._reapplying_layout = True
        try:
            self.layouts.reapply(preserve_view=True)
        finally:
            self._reapplying_layout = False

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
            file_text=tr(
                "window.file_points_status",
                file_name=self.session.file_name, point_count=self.session.point_count,
            ),
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
        font_id, font_italic, font_lineweight_mm = self.fonts_panel.get_state()
        configs = [
            self.panel.build_generation_config(
                mode, self.session.quantum, font_id, font_italic, font_lineweight_mm
            )
            for mode in draw_modes
        ]
        commands = self.survey_draw_service.build_commands(self.session.data, selected_numbers, configs)
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
            self.session.fail(tr("window.could_not_draw", error=exc))
            self.refresh()
            return
        self.session.mark_applied()
        self.documents.refresh_dxf_source()
        self.refresh()

    def _on_apply_font_to_all(self) -> None:
        font_id, font_italic, font_lineweight_mm = self.fonts_panel.get_state()
        doc = self.dxf_viewer.ensure_document()
        count = len(doc.all_text_handles())
        self.dxf_viewer.execute_command(ApplyFontToAllTextCommand(font_id, font_italic, font_lineweight_mm))
        self.documents.refresh_dxf_source()
        self.flash_status(tr("fonts_panel.applied_status", count=count))
        self.refresh()

    def refresh_table_template_bindings(self) -> None:
        sheet_fields = [f for f in self.table_template.fields if f.scope == "sheet"]
        project_fields = [f for f in self.table_template.fields if f.scope == "project"]
        self.layout_panel.sheet_fields_tab.rebuild(sheet_fields)
        self.layout_panel.project_fields_tab.rebuild(project_fields)
        self.layout_panel.project_fields_tab.set_values(self.table_template.project_field_values)
        self.layouts.refresh()

    def open_start_screen(self) -> None:
        self.router.start_screen()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        dialog.exec()
        if dialog.language_changed():
            self.router.editor(initial_state=self.project.current_state(), project_path=self.project.path)

    def new_project(self) -> None:
        self.router.editor()

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("window.open_dialog_title"),
            "",
            f"{project_io.PROJECT_FILE_FILTER};;{tr('common.dxf_filter')};;{tr('common.txt_filter')}",
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            self.router.open_path(self.settings, path)
        except ProjectFileError as exc:
            self.flash_status(str(exc))
