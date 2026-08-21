from __future__ import annotations

import os
from dataclasses import asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import project as project_io
from core.commands.composite import CompositeCommand
from core.config import CableOptions, GenerationConfig, HeightsOptions, PipeOptions, PointsOptions
from core.draw_modes import DrawMode
from core.exceptions import AppError, ProjectFileError
from core.parser import PointFileParser
from core.project import (
    CableState,
    DelimiterState,
    HeightsState,
    LayerDefState,
    LayerOnlyState,
    LayerState,
    PipeState,
    PointsState,
    ProjectState,
    SelectionState,
)
from core.survey_draw_service import SurveyDrawService
from core.validation import ensure_draw_modes, ensure_has_data, ensure_selection
from models.point import Point
from ui.assets import ICON_PATH
from ui.dxf_viewer import DxfViewer
from ui.recent_projects import add_recent_project, list_recent_projects, remove_recent_project
from ui.style import APP_STYLESHEET
from ui.tabs.cable_tab import CableTab
from ui.tabs.delimiter_tab import DelimiterTab
from ui.tabs.draw_tab import DrawTab
from ui.tabs.heights_tab import HeightsTab
from ui.tabs.layer_only_tab import LayerOnlyTab
from ui.tabs.layer_tab import LayerTab
from ui.tabs.pipe_tab import PipeTab
from ui.tabs.points_tab import PointsTab
from ui.tabs.selection_tab import SelectionTab
from ui.theme import (
    LEFT_COLUMN_MAX_WIDTH,
    LEFT_COLUMN_MIN_WIDTH,
    LEFT_COLUMN_WIDTH,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
)
from ui.widgets import (
    Accordion,
    AccordionSection,
    Card,
    DropZone,
    DxfSourceRow,
    ErrorBanner,
    FileCard,
    SegmentedControl,
    restyle,
)

_DELIMITER_DISPLAY = {"auto": "Auto", "space": "Space", "tab": "Tab"}
_STATUS_TEXT = {
    "empty": "Empty",
    "ready": "Ready",
    "applied": "Applied",
    "error": "Errors: 1",
}
# Characters Windows forbids in a filename — a renamed project's file must
# still be a legal name on disk (see MainWindow.rename_project).
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class _PointFileSection(QWidget):
    """The point-file accordion section's content: the upload widget on
    top, the delimiter options below (hidden until a file is loaded).
    is_modified() delegates to the delimiter tab, since the file widget
    itself is never "modified" in the option-tab sense."""

    def __init__(self, file_stack: QStackedWidget, delimiter_tab: DelimiterTab) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_LG)
        layout.addWidget(file_stack)
        layout.addWidget(delimiter_tab)
        self._delimiter_tab = delimiter_tab

    def is_modified(self) -> bool:
        return self._delimiter_tab.is_modified()


class AppState(Enum):
    """The four states the shell can be in, driving the status bar."""

    EMPTY = "empty"
    READY = "ready"
    APPLIED = "applied"
    ERROR = "error"


class MainWindow(QMainWindow):

    def __init__(
        self, initial_state: Optional[ProjectState] = None, project_path: Optional[str] = None
    ) -> None:
        super().__init__()
        self.setWindowTitle("Geodetic Sketch Generator")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)
        # Starts maximized regardless of which of the several call sites
        # ends up calling .show() on it (New Project, Open Project, the
        # launcher's Open…) - setting this before the first show is honored
        # without needing to touch each of those separately. The launcher
        # (StartScreen) is unaffected - it opens at its own normal size.
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.settings = QtCore.QSettings("acsg", "acsg_pro")

        self.parser = PointFileParser()
        self.survey_draw_service = SurveyDrawService()

        self.file_path: str = ""
        self.file_size_text: str = ""
        self.data: Dict[int, Point] = {}
        self.dxf_path: str = ""
        self._has_applied = False
        self._last_error: Optional[str] = None
        self._sections: List[Tuple[AccordionSection, QWidget]] = []
        # None until the project has been saved at least once (or was
        # opened from an existing .gsgproj) - see save_project/save_project_as.
        self.project_path: Optional[str] = project_path
        self.project_name: str = initial_state.name if initial_state is not None else "Untitled"
        # Kept alive here once opened so Qt doesn't garbage-collect it — see
        # new_project/_open_path_in_new_window/open_start_screen.
        self._sibling_window: Optional[QMainWindow] = None

        self._build_ui()
        self._wire_signals()
        self.setStyleSheet(APP_STYLESHEET)
        if initial_state is not None:
            self.load_project_state(initial_state)
        if self.project_path:
            self.setWindowTitle(f"Geodetic Sketch Generator — {self.project_name}")
        self._refresh()

    # ==================================================================
    # UI BUILD
    # ==================================================================
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        content_layout.setSpacing(0)

        # A draggable splitter, not a fixed-width column — lets the user
        # resize the left panel like a dockable panel in GIMP/VS Code/AutoCAD.
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(SPACE_LG)
        # Built right-first: the left column's "Layers" nav item docks
        # dxf_viewer.layer_panel, so dxf_viewer has to exist already.
        right_column = self._build_right_column()
        self.main_splitter.addWidget(self._build_left_column())
        self.main_splitter.addWidget(right_column)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        saved_width = self.settings.value("ui/leftColumnWidth", LEFT_COLUMN_WIDTH, type=int)
        self.main_splitter.setSizes([saved_width, max(1, 1000 - saved_width)])
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)
        content_layout.addWidget(self.main_splitter)
        root.addWidget(content, 1)

        root.addWidget(self._build_status_bar())

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_SM)

        layout.addWidget(self._build_logo())
        layout.addWidget(self._build_file_button())
        layout.addWidget(self._build_edit_button())
        layout.addStretch(1)
        return bar

    @staticmethod
    def _build_logo() -> QLabel:
        logo = QLabel()
        logo.setObjectName("topBarLogo")
        pixmap = QPixmap(ICON_PATH)
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        return logo

    def _build_file_button(self) -> QPushButton:
        """A single "File ▾" button replacing separate Projects/Save Project
        buttons — an AutoCAD-style application menu covering the whole
        project lifecycle (new/open/recent/save/export/close) in one place."""
        btn = self._make_button("File  ▾", "secondary", None)
        menu = QMenu(btn)
        menu.setObjectName("fileMenu")
        menu.addAction("New Project", self.new_project)
        menu.addAction("Open Project…", self.open_project_dialog)
        self._recent_menu = menu.addMenu("Open Recent")
        menu.aboutToShow.connect(self._refresh_recent_menu)
        menu.addSeparator()
        menu.addAction("Save Project", self.save_project)
        menu.addAction("Save Project As…", self.save_project_as)
        menu.addAction("Rename Project…", self.rename_project)
        menu.addAction("Export DXF…", self.save_dxf)
        menu.addSeparator()
        menu.addAction("Close Project", self.open_start_screen)
        btn.setMenu(menu)
        return btn

    def _build_edit_button(self) -> QPushButton:
        """A single "Edit ▾" button holding Undo/Redo — the DXF panel's own
        toolbar buttons for these were removed in favor of consolidating
        them here, next to File. Ctrl+Z/Ctrl+Y keep working exactly as
        before (they're handled by DxfViewer's own window-scoped
        shortcuts) — these menu actions deliberately have no shortcut of
        their own attached, to avoid registering the same key combination
        twice on the same window."""
        btn = self._make_button("Edit  ▾", "secondary", None)
        menu = QMenu(btn)
        menu.setObjectName("editMenu")
        self._undo_action = menu.addAction("Undo (Ctrl+Z)", lambda: self.dxf_viewer.echo(self.dxf_viewer.undo()))
        self._redo_action = menu.addAction("Redo (Ctrl+Y)", lambda: self.dxf_viewer.echo(self.dxf_viewer.redo()))
        menu.aboutToShow.connect(self._sync_edit_menu)
        btn.setMenu(menu)
        return btn

    def _sync_edit_menu(self) -> None:
        self._undo_action.setEnabled(self.dxf_viewer.can_undo())
        self._redo_action.setEnabled(self.dxf_viewer.can_redo())

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        paths = list_recent_projects(self.settings)
        if not paths:
            placeholder = self._recent_menu.addAction("No recent projects")
            placeholder.setEnabled(False)
            return
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            self._recent_menu.addAction(name, lambda checked=False, p=path: self._open_path_in_new_window(p))

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self.settings.setValue("ui/leftColumnWidth", self.main_splitter.sizes()[0])

    def _build_left_column(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setMinimumWidth(LEFT_COLUMN_MIN_WIDTH)
        wrapper.setMaximumWidth(LEFT_COLUMN_MAX_WIDTH)
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE_LG)

        self.dxf_source_row = DxfSourceRow()
        self.dxf_source_row.fileRequested.connect(self.select_dxf_file)
        self.dxf_source_row.filesDropped.connect(self._on_dxf_files_dropped)
        self.dxf_source_row.clearRequested.connect(self.clear_dxf_file)
        outer.addWidget(self.dxf_source_row)

        # GIMP-style dock switcher: the user picks which of these two shows
        # below, independent of whether a point file or DXF is loaded.
        self.left_nav = SegmentedControl([("point_file", "Point File"), ("layers", "Layers")])
        outer.addWidget(self.left_nav)

        self.left_stack = QStackedWidget()

        self.file_stack = QStackedWidget()
        self.drop_zone = DropZone()
        self.drop_zone.fileRequested.connect(self.select_file)
        self.drop_zone.filesDropped.connect(self._on_files_dropped)
        self.file_card = FileCard()
        self.file_card.changeRequested.connect(self.select_file)
        self.file_stack.addWidget(self.drop_zone)
        self.file_stack.addWidget(self.file_card)

        self.delimiter_tab = DelimiterTab()
        self.draw_tab = DrawTab()
        self.layer_tab = LayerTab(self.settings)
        self.points_tab = PointsTab()
        self.lines_tab = LayerOnlyTab()
        self.plines_tab = LayerOnlyTab()
        self.poly3d_tab = LayerOnlyTab()
        self.heights_tab = HeightsTab()
        self.cable_tab = CableTab()
        self.pipe_tab = PipeTab()
        self.selection_tab = SelectionTab()
        self._layer_dependent_tabs = (
            self.points_tab,
            self.lines_tab,
            self.plines_tab,
            self.poly3d_tab,
            self.heights_tab,
            self.cable_tab,
            self.pipe_tab,
        )
        self._sync_layer_dropdowns()  # seeds each dropdown above with the initial layer list

        self.accordion = Accordion()
        # A 4th element names the Drawing Mode key (see ui.tabs.draw_tab)
        # that gates this section's visibility - None for sections that
        # aren't tied to one (see _refresh).
        specs = (
            ("▭", "Point File", _PointFileSection(self.file_stack, self.delimiter_tab), None),
            ("✎", "Drawing Mode", self.draw_tab, None),
            ("▤", "Layer", self.layer_tab, None),
            ("○", "Points", self.points_tab, "points"),
            ("╲", "Lines", self.lines_tab, "lines"),
            ("∿", "PLines", self.plines_tab, "plines"),
            ("◇", "3DPOLY", self.poly3d_tab, "3dpoly"),
            ("☰", "Heights", self.heights_tab, "heights"),
            ("╱", "Cable Marks", self.cable_tab, "cable"),
            ("═", "Pipe", self.pipe_tab, "pipe"),
            ("▢", "Selection", self.selection_tab, None),
        )
        self._mode_sections: Dict[str, AccordionSection] = {}
        for icon, title, tab, mode_key in specs:
            section = AccordionSection(icon, title, tab)
            self.accordion.add_section(section)
            self._sections.append((section, tab))
            if mode_key is not None:
                self._mode_sections[mode_key] = section
        self._section_mode_key = {section: key for key, section in self._mode_sections.items()}
        # The point-file section holds its own upload controls, so it must
        # stay visible even with nothing loaded yet - the rest are hidden
        # until there's data to mean anything (see _refresh).
        self._point_file_section = self._sections[0][0]
        # Layer only means something once a drawing mode is actually
        # checked - hidden the rest of the time (see _refresh).
        self._layer_section = self._sections[2][0]

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.accordion)
        self.left_stack.addWidget(scroll)

        layers_scroll = QScrollArea()
        layers_scroll.setWidgetResizable(True)
        layers_scroll.setFrameShape(QFrame.Shape.NoFrame)
        layers_scroll.setWidget(self.dxf_viewer.layer_panel)
        self.left_stack.addWidget(layers_scroll)

        self.left_nav.currentChanged.connect(
            lambda key: self.left_stack.setCurrentIndex(0 if key == "point_file" else 1)
        )
        outer.addWidget(self.left_stack, 1)

        return wrapper

    def _build_right_column(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        header = QHBoxLayout()
        header.setSpacing(SPACE_SM)
        self.preview_title = QLabel("DXF preview")
        self.preview_title.setObjectName("previewHeaderTitle")
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("previewMeta")
        header.addWidget(self.preview_title)
        header.addWidget(self.preview_meta)
        header.addStretch(1)
        layout.addLayout(header)

        self.error_banner = ErrorBanner()
        layout.addWidget(self.error_banner)

        self.dxf_viewer = DxfViewer()
        layout.addWidget(self.dxf_viewer, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(SPACE_SM)
        self.save_button = self._make_button("Save DXF", "secondary", self.save_dxf)
        self.apply_button = self._make_button("Apply to DXF  →", "primary", self.apply_to_dxf)
        button_row.addWidget(self.save_button)
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        layout.addLayout(button_row)

        return card

    @staticmethod
    def _make_button(text: str, variant: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("btn")
        btn.setProperty("variant", variant)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if slot is not None:
            btn.clicked.connect(slot)
        return btn

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SPACE_XL, SPACE_SM, SPACE_XL, SPACE_SM)
        layout.setSpacing(SPACE_LG)

        self.status_file_label = QLabel("")
        self.status_file_label.setObjectName("statusText")
        self.status_layer_label = QLabel("")
        self.status_layer_label.setObjectName("statusText")
        self.status_delim_label = QLabel("")
        self.status_delim_label.setObjectName("statusText")
        self.status_state_label = QLabel("")
        self.status_state_label.setObjectName("statusText")

        layout.addWidget(self.status_file_label)
        layout.addWidget(self.status_layer_label)
        layout.addWidget(self.status_delim_label)
        layout.addStretch(1)
        layout.addWidget(self.status_state_label)
        return bar

    # ==================================================================
    # SIGNAL WIRING
    # ==================================================================
    def _wire_signals(self) -> None:
        self.delimiter_tab.swap_xy_toggled.connect(self._on_config_changed)
        self.delimiter_tab.cabinet_mode_toggled.connect(self._on_config_changed)
        self.delimiter_tab.delimiter_changed.connect(self._on_delimiter_changed)

        self.draw_tab.modes_changed.connect(self._on_config_changed)
        self.points_tab.numbers_toggled.connect(self._on_config_changed)
        self.points_tab.option_changed.connect(self._on_config_changed)
        self.lines_tab.option_changed.connect(self._on_config_changed)
        self.plines_tab.option_changed.connect(self._on_config_changed)
        self.poly3d_tab.option_changed.connect(self._on_config_changed)
        self.heights_tab.option_changed.connect(self._on_config_changed)
        self.cable_tab.option_changed.connect(self._on_config_changed)
        self.pipe_tab.option_changed.connect(self._on_config_changed)
        self.selection_tab.selection_changed.connect(self._on_config_changed)
        self.layer_tab.layers_changed.connect(self._on_layers_changed)

        self.dxf_viewer.documentChanged.connect(self._refresh)

    # ==================================================================
    # STATE
    # ==================================================================
    def _current_state(self) -> AppState:
        if self._last_error:
            return AppState.ERROR
        if not self.file_path:
            return AppState.EMPTY
        if self._has_applied:
            return AppState.APPLIED
        return AppState.READY

    def _on_config_changed(self, *_args) -> None:
        # Whatever was last applied to the DXF no longer matches these
        # settings, so the "Applied" status would be misleading until the
        # user presses Apply again.
        self._has_applied = False
        self._refresh()

    def _sync_layer_dropdowns(self) -> None:
        """Pushes the Layer section's current list into every dependent
        tab's own layer picker — called whenever that list changes, and
        once up front to seed them (see _build_left_column)."""
        names = self.layer_tab.layer_names()
        default = self.layer_tab.default_layer_name()
        for tab in self._layer_dependent_tabs:
            tab.set_available_layers(names, default)

    def _on_layers_changed(self) -> None:
        self._sync_layer_dropdowns()
        self._on_config_changed()

    def _on_delimiter_changed(self) -> None:
        if self.file_path:
            self._reparse_current_file()
        self._on_config_changed()

    # ==================================================================
    # RENDERING
    # ==================================================================
    def _refresh(self) -> None:
        state = self._current_state()

        has_file = state is not AppState.EMPTY
        checked_modes = set(self.draw_tab.mode_keys)
        self.delimiter_tab.setVisible(has_file)
        for section, _tab in self._sections:
            if section is self._point_file_section:
                continue
            mode_key = self._section_mode_key.get(section)
            if mode_key is not None:
                # Points/Lines/PLines/3DPOLY/Heights/Cable Marks/Pipe: only
                # worth showing once that exact mode is actually checked.
                section.setVisible(has_file and mode_key in checked_modes)
            elif section is self._layer_section:
                section.setVisible(has_file and bool(checked_modes))
            else:
                section.setVisible(has_file)

        if state is AppState.EMPTY:
            self.file_stack.setCurrentWidget(self.drop_zone)
            self.error_banner.clear()
            file_label = "No file selected"
            layer_text = "Layer: –"
            delim_text = "Delimiter: –"
        else:
            name, count, size = os.path.basename(self.file_path), len(self.data), self.file_size_text
            self.file_card.set_file(name, count, size)
            self.file_stack.setCurrentWidget(self.file_card)
            file_label = f"{name} · {count} points"
            layer_text = f"Layer: {self.layer_tab.default_layer_name()}"
            delim_text = f"Delimiter: {self._delimiter_display_name()}"

            if state in (AppState.READY, AppState.APPLIED):
                self.error_banner.clear()
            else:  # ERROR
                self.error_banner.show_message(self._last_error)

        self.status_file_label.setText(file_label)
        self.status_layer_label.setText(layer_text)
        self.status_delim_label.setText(delim_text)
        self.status_state_label.setText(_STATUS_TEXT[state.value])
        self.status_state_label.setProperty("variant", "error" if state is AppState.ERROR else "normal")
        restyle(self.status_state_label)

        self.save_button.setEnabled(self.dxf_viewer.has_document)
        self.apply_button.setEnabled(state is not AppState.EMPTY)

        self._refresh_preview_panel()
        self._refresh_modified_dots()

    def _refresh_preview_panel(self) -> None:
        if self.dxf_viewer.has_document:
            self.preview_meta.setText(
                f"{self.dxf_viewer.entity_count} entities · {self.dxf_viewer.layer_count} layers"
            )
        else:
            self.preview_meta.setText("")

    def _delimiter_display_name(self) -> str:
        key = self.delimiter_tab.gap_control.current() or "auto"
        return _DELIMITER_DISPLAY.get(key, "Auto")

    def _refresh_modified_dots(self) -> None:
        for section, tab in self._sections:
            is_modified = tab.is_modified() if hasattr(tab, "is_modified") else False
            section.set_modified(is_modified)

    def _flash_status(self, message: str, ms: int = 2500) -> None:
        self.status_state_label.setText(message)
        QtCore.QTimer.singleShot(ms, self._refresh)

    # ==================================================================
    # HELPERS
    # ==================================================================
    # Modes with their own options tab target whichever layer that tab's
    # dropdown currently shows; the rest (Lines/PLines/3DPOLY have no
    # options tab of their own) fall back to the Layer section's default.
    _LAYER_PICKER_TABS = {
        DrawMode.POINTS: "points_tab",
        DrawMode.LINES: "lines_tab",
        DrawMode.PLINES: "plines_tab",
        DrawMode.POLY3D: "poly3d_tab",
        DrawMode.HEIGHTS: "heights_tab",
        DrawMode.CABLE_MARKS: "cable_tab",
        DrawMode.PIPE: "pipe_tab",
    }

    def _layer_name_for_mode(self, draw_mode: DrawMode) -> str:
        tab_name = self._LAYER_PICKER_TABS.get(draw_mode)
        if tab_name is not None:
            return getattr(self, tab_name).get_layer_name()
        return self.layer_tab.default_layer_name()

    def _build_generation_config(self, layer_name: str, draw_mode: DrawMode) -> GenerationConfig:
        return GenerationConfig(
            layer_name=layer_name,
            draw_mode=draw_mode,
            cabinet_mode=self.delimiter_tab.cabinet_mode_enabled,
            points=self.points_tab.get_options(),
            heights=self.heights_tab.get_options(),
            cable=self.cable_tab.get_options(),
            pipe=self.pipe_tab.get_options(),
            layer_rgb=self.layer_tab.get_rgb(layer_name),
        )

    @staticmethod
    def _format_size(path: str) -> str:
        try:
            size = os.path.getsize(path)
        except OSError:
            return ""
        if size < 1024:
            return f"{size} B"
        kb = size / 1024
        if kb < 1024:
            return f"{kb:.0f} KB"
        return f"{kb / 1024:.1f} MB"

    # ==================================================================
    # IO
    # ==================================================================
    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open TXT File", "", "Text Files (*.txt)")
        if not file_path:
            return
        self._load_file(file_path)

    def _on_files_dropped(self, paths: List[str]) -> None:
        txt_paths = [p for p in paths if p.lower().endswith(".txt")]
        if txt_paths:
            self._load_file(txt_paths[0])

    def _load_file(self, file_path: str) -> None:
        # Record the real file/size up front, even if parsing below fails —
        # the UI should always reflect the real file that was picked, never
        # fall back to sample data once the user has actually chosen one.
        self.file_path = file_path
        self.file_size_text = self._format_size(file_path)
        try:
            self.data = self.parser.parse_file(file_path, self.delimiter_tab.delimiter_mode)
        except AppError as exc:
            self.data = {}
            self._last_error = str(exc)
            self._has_applied = False
            self._refresh()
            return
        self._has_applied = False
        self._last_error = None
        self._refresh()

    def _reparse_current_file(self) -> None:
        try:
            self.data = self.parser.parse_file(self.file_path, self.delimiter_tab.delimiter_mode)
            self._last_error = None
        except AppError as exc:
            self.data = {}
            self._last_error = str(exc)
        self._has_applied = False

    # ==================================================================
    # DXF PREVIEW
    # ==================================================================
    def select_dxf_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open DXF File", "", "DXF Files (*.dxf)")
        if not file_path:
            return
        self._load_dxf_file(file_path)

    def _on_dxf_files_dropped(self, paths: List[str]) -> None:
        dxf_paths = [p for p in paths if p.lower().endswith(".dxf")]
        if dxf_paths:
            self._load_dxf_file(dxf_paths[0])

    def _load_dxf_file(self, file_path: str) -> None:
        ok, message = self.dxf_viewer.load_file(file_path)
        if not ok:
            self.dxf_source_row.show_error(message)
            return
        self.dxf_path = file_path
        self._has_applied = False  # the newly loaded document hasn't had the current settings applied yet
        self.dxf_source_row.set_file(os.path.basename(file_path), self.dxf_viewer.entity_count)
        self._refresh()

    def _load_dxf_from_text(self, content: str, file_path: str) -> None:
        """Restores the DXF from an embedded project snapshot (see
        core.project.ProjectState.dxf_content) instead of reading a file
        from disk — `file_path` is kept only as the "Save DXF" default
        location/display name, exactly like _load_dxf_file's bookkeeping."""
        ok, message = self.dxf_viewer.load_from_text(content)
        if not ok:
            self.dxf_source_row.show_error(message)
            return
        self.dxf_path = file_path
        self._has_applied = False
        name = os.path.basename(file_path) if file_path else "Untitled drawing"
        self.dxf_source_row.set_file(name, self.dxf_viewer.entity_count)
        self._refresh()

    def clear_dxf_file(self) -> None:
        self.dxf_path = ""
        self._has_applied = False
        self.dxf_viewer.clear()
        self.dxf_source_row.set_empty()
        self._refresh()

    # ==================================================================
    # APPLY TO DXF
    # ==================================================================
    def apply_to_dxf(self) -> None:
        self.layer_tab.persist(self.settings)
        try:
            ensure_has_data(self.data, self.file_path)
            selected_numbers = self.selection_tab.get_selected_numbers(self.data)
            ensure_selection(selected_numbers)
            draw_modes = self.draw_tab.draw_modes
            ensure_draw_modes(draw_modes)
            # Each checked mode becomes its own command, targeting whichever
            # layer that mode's own picker is set to, all bundled into one
            # undo step - so e.g. PLines + Heights marks + Cable marks apply
            # (and later undo) together as a single Apply.
            commands = [
                self.survey_draw_service.build_command(
                    self.data,
                    selected_numbers,
                    self._build_generation_config(self._layer_name_for_mode(mode), mode),
                )
                for mode in draw_modes
            ]
            command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
        except AppError as exc:
            self._last_error = str(exc)
            self._has_applied = False
            self._refresh()
            return
        self._last_error = None
        try:
            self.dxf_viewer.execute_command(command)
        except Exception as exc:  # noqa: BLE001 - drawing into the DXF must never crash the app
            self._last_error = f"Could not draw into the DXF file: {exc}"
            self._has_applied = False
            self._refresh()
            return
        self._has_applied = True
        if not self.dxf_path:
            self.dxf_source_row.set_file("Untitled drawing", self.dxf_viewer.entity_count)
        else:
            self.dxf_source_row.set_file(os.path.basename(self.dxf_path), self.dxf_viewer.entity_count)
        self._refresh()

    # ==================================================================
    # UTIL
    # ==================================================================
    def save_dxf(self) -> None:
        if not self.dxf_viewer.has_document:
            return
        suggested = os.path.basename(self.dxf_path) if self.dxf_path else "drawing.dxf"
        path, _ = QFileDialog.getSaveFileName(self, "Save DXF", suggested, "DXF Files (*.dxf)")
        if not path:
            return
        self.dxf_viewer.save_document(path)
        self.dxf_path = path
        self.dxf_source_row.set_file(os.path.basename(path), self.dxf_viewer.entity_count)
        self._flash_status(f"Saved to {os.path.basename(path)}")

    # ==================================================================
    # PROJECT SAVE / LOAD — see core/project.py for the .gsgproj format and
    # ui/start_screen.py for the AutoCAD-style launcher that opens one.
    # ==================================================================
    def collect_project_state(self) -> ProjectState:
        """Every tab's current settings plus the point/DXF file paths, as
        one serializable ProjectState — see core.project."""
        separate_text, range_text = self.selection_tab.get_expression_state()
        layers, default_name = self.layer_tab.get_state()
        return ProjectState(
            name=self.project_name or project_io.default_project_name(self.file_path, self.dxf_path),
            txt_file_path=self.file_path,
            dxf_file_path=self.dxf_path,
            dxf_content=self.dxf_viewer.to_dxf_text(),
            draw_modes=self.draw_tab.mode_keys,
            delimiter=DelimiterState(
                mode=self.delimiter_tab.gap_key,
                swap_xy=self.delimiter_tab.swap_xy_enabled,
                cabinet_mode=self.delimiter_tab.cabinet_mode_enabled,
            ),
            points=PointsState(**asdict(self.points_tab.get_options()), layer_name=self.points_tab.get_layer_name()),
            lines=LayerOnlyState(layer_name=self.lines_tab.get_layer_name()),
            plines=LayerOnlyState(layer_name=self.plines_tab.get_layer_name()),
            poly3d=LayerOnlyState(layer_name=self.poly3d_tab.get_layer_name()),
            heights=HeightsState(
                **asdict(self.heights_tab.get_options()), layer_name=self.heights_tab.get_layer_name()
            ),
            cable=CableState(**asdict(self.cable_tab.get_options()), layer_name=self.cable_tab.get_layer_name()),
            pipe=PipeState(**asdict(self.pipe_tab.get_options()), layer_name=self.pipe_tab.get_layer_name()),
            selection=SelectionState(
                mode=self.selection_tab.mode_key, separate_text=separate_text, range_text=range_text
            ),
            layer=LayerState(
                layers=[LayerDefState(name=name, rgb=rgb) for name, rgb in layers], default_name=default_name
            ),
        )

    def load_project_state(self, state: ProjectState) -> None:
        """Restores every tab from a saved project, then restores the DXF
        (from its embedded snapshot if the project has one — see
        core.project.ProjectState.dxf_content — falling back to re-reading
        dxf_file_path from disk for older/imported projects that don't) and
        the point file, if still present on disk. A missing file is skipped
        rather than treated as a failure, since the rest of the project is
        still worth restoring."""
        self.project_name = state.name
        self.delimiter_tab.set_state(state.delimiter.mode, state.delimiter.swap_xy, state.delimiter.cabinet_mode)
        self.draw_tab.set_mode_keys(state.draw_modes)
        self.layer_tab.set_state([(l.name, tuple(l.rgb)) for l in state.layer.layers], state.layer.default_name)
        self._sync_layer_dropdowns()  # populate each tab's picker before selecting a specific layer_name below
        self.points_tab.set_options(
            PointsOptions(
                numbers_enabled=state.points.numbers_enabled,
                font_size=state.points.font_size,
                diameter=state.points.diameter,
            )
        )
        self.points_tab.set_layer_name(state.points.layer_name)
        self.lines_tab.set_layer_name(state.lines.layer_name)
        self.plines_tab.set_layer_name(state.plines.layer_name)
        self.poly3d_tab.set_layer_name(state.poly3d.layer_name)
        self.heights_tab.set_options(
            HeightsOptions(font_size=state.heights.font_size, frequency=state.heights.frequency)
        )
        self.heights_tab.set_layer_name(state.heights.layer_name)
        self.cable_tab.set_options(
            CableOptions(
                font_size=state.cable.font_size, frequency=state.cable.frequency, marks_text=state.cable.marks_text
            )
        )
        self.cable_tab.set_layer_name(state.cable.layer_name)
        self.pipe_tab.set_options(PipeOptions(width=state.pipe.width))
        self.pipe_tab.set_layer_name(state.pipe.layer_name)
        self.selection_tab.set_state(state.selection.mode, state.selection.separate_text, state.selection.range_text)

        missing = []
        if state.txt_file_path:
            if os.path.exists(state.txt_file_path):
                self._load_file(state.txt_file_path)
            else:
                missing.append(os.path.basename(state.txt_file_path))
        if state.dxf_content:
            self._load_dxf_from_text(state.dxf_content, state.dxf_file_path)
        elif state.dxf_file_path:
            if os.path.exists(state.dxf_file_path):
                self._load_dxf_file(state.dxf_file_path)
            else:
                missing.append(os.path.basename(state.dxf_file_path))
        if missing:
            self._flash_status(f"Could not find: {', '.join(missing)} (rest of the project was restored)", ms=5000)

    def save_project(self) -> None:
        if not self.project_path:
            self.save_project_as()
            return
        self._save_project_to(self.project_path, self.collect_project_state())

    def save_project_as(self) -> None:
        state = self.collect_project_state()
        suggested = (self.project_name or project_io.default_project_name(self.file_path, self.dxf_path))
        suggested += project_io.PROJECT_FILE_EXTENSION
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", suggested, project_io.PROJECT_FILE_FILTER)
        if not path:
            return
        if not path.lower().endswith(project_io.PROJECT_FILE_EXTENSION):
            path += project_io.PROJECT_FILE_EXTENSION
        state.name = os.path.splitext(os.path.basename(path))[0]
        self._save_project_to(path, state)

    def _save_project_to(self, path: str, state: ProjectState) -> None:
        try:
            project_io.save_project(path, state)
        except ProjectFileError as exc:
            self._flash_status(str(exc))
            return
        self.project_path = path
        self.project_name = state.name
        self.setWindowTitle(f"Geodetic Sketch Generator — {self.project_name}")
        add_recent_project(self.settings, path)
        self._flash_status(f"Saved project {os.path.basename(path)}")

    def rename_project(self) -> None:
        """Renames the project — and, if it's already been saved, the
        .gsgproj file itself on disk, keeping the two in sync (an unsaved
        project just gets the new name to save under next time)."""
        new_name, ok = QInputDialog.getText(self, "Rename Project", "Project name:", text=self.project_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == self.project_name:
            return
        if any(ch in _INVALID_FILENAME_CHARS for ch in new_name):
            QMessageBox.warning(
                self, "Rename Project", f"A project name can't contain any of: {_INVALID_FILENAME_CHARS}"
            )
            return

        if self.project_path:
            new_path = os.path.join(
                os.path.dirname(self.project_path), new_name + project_io.PROJECT_FILE_EXTENSION
            )
            already_taken = os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(
                self.project_path
            )
            if already_taken:
                QMessageBox.warning(
                    self, "Rename Project", f'A project named "{new_name}" already exists in this folder.'
                )
                return
            try:
                os.replace(self.project_path, new_path)
            except OSError as exc:
                self._flash_status(f"Could not rename project file: {exc}")
                return
            remove_recent_project(self.settings, self.project_path)
            self.project_path = new_path
            add_recent_project(self.settings, new_path)

        self.project_name = new_name
        self.setWindowTitle(f"Geodetic Sketch Generator — {self.project_name}")
        self._flash_status(f"Renamed to {new_name}")

    def open_start_screen(self) -> None:
        from ui.start_screen import StartScreen  # local import: start_screen imports MainWindow itself

        self._sibling_window = StartScreen()
        self._sibling_window.show()
        self.close()

    def new_project(self) -> None:
        self._sibling_window = MainWindow()
        self._sibling_window.show()
        self.close()

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "", f"{project_io.PROJECT_FILE_FILTER};;DXF Files (*.dxf);;Text Files (*.txt)"
        )
        if not path:
            return
        self._open_path_in_new_window(path)

    def _open_path_in_new_window(self, path: str) -> None:
        try:
            state = project_io.open_any(path)
        except ProjectFileError as exc:
            self._flash_status(str(exc))
            return
        opened_project_path = project_io.project_path_if_saved(path)
        if opened_project_path is not None:
            add_recent_project(self.settings, opened_project_path)
        self._sibling_window = MainWindow(initial_state=state, project_path=opened_project_path)
        self._sibling_window.show()
        self.close()
