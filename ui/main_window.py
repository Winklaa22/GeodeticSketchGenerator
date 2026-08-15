from __future__ import annotations

import os
from enum import Enum
from typing import Dict, List, Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import GenerationConfig
from core.exceptions import AppError
from core.parser import PointFileParser
from core.survey_draw_service import SurveyDrawService
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point
from ui.dxf_viewer import DxfViewer
from ui.style import APP_STYLESHEET
from ui.tabs.cable_tab import CableTab
from ui.tabs.delimiter_tab import DelimiterTab
from ui.tabs.draw_tab import DrawTab
from ui.tabs.heights_tab import HeightsTab
from ui.tabs.layer_tab import LayerTab
from ui.tabs.points_tab import PointsTab
from ui.tabs.selection_tab import SelectionTab
from ui.theme import LEFT_COLUMN_WIDTH, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XL
from ui.widgets import (
    Accordion,
    AccordionSection,
    Card,
    DropZone,
    DxfSourceRow,
    ErrorBanner,
    FileCard,
    Tag,
    WorkflowStepper,
    restyle,
)

_DELIMITER_DISPLAY = {"auto": "Auto", "space": "Space", "tab": "Tab"}
_STATUS_TEXT = {
    "empty": "Empty",
    "ready": "Ready",
    "applied": "Applied",
    "error": "Errors: 1",
}


class AppState(Enum):
    """The four states the shell can be in, driving the stepper/status bar."""

    EMPTY = "empty"
    READY = "ready"
    APPLIED = "applied"
    ERROR = "error"


class MainWindow(QMainWindow):

    STEP_NAMES = ("Load file", "Configure", "Preview", "Export")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Geodetic Sketch Generator")
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)
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

        self._build_ui()
        self._wire_signals()
        self.setStyleSheet(APP_STYLESHEET)
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

        self.stepper = WorkflowStepper(self.STEP_NAMES)
        root.addWidget(self.stepper)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        content_layout.setSpacing(SPACE_XL)
        content_layout.addWidget(self._build_left_column())
        content_layout.addWidget(self._build_right_column(), 1)
        root.addWidget(content, 1)

        root.addWidget(self._build_status_bar())

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        title = QLabel('Geodetic Sketch Generator <span style="color:#9184d9;">PRO</span>')
        title.setObjectName("appTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        version_tag = Tag("v3.2", variant="neutral")

        layout.addWidget(title)
        layout.addWidget(version_tag)
        layout.addStretch(1)
        return bar

    def _build_left_column(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setFixedWidth(LEFT_COLUMN_WIDTH)
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE_LG)

        self.file_stack = QStackedWidget()
        self.drop_zone = DropZone()
        self.drop_zone.fileRequested.connect(self.select_file)
        self.drop_zone.filesDropped.connect(self._on_files_dropped)
        self.file_card = FileCard()
        self.file_card.changeRequested.connect(self.select_file)
        self.file_stack.addWidget(self.drop_zone)
        self.file_stack.addWidget(self.file_card)
        outer.addWidget(self.file_stack)

        self.dxf_source_row = DxfSourceRow()
        self.dxf_source_row.fileRequested.connect(self.select_dxf_file)
        self.dxf_source_row.filesDropped.connect(self._on_dxf_files_dropped)
        self.dxf_source_row.clearRequested.connect(self.clear_dxf_file)
        outer.addWidget(self.dxf_source_row)

        self.delimiter_tab = DelimiterTab()
        self.draw_tab = DrawTab()
        self.points_tab = PointsTab()
        self.heights_tab = HeightsTab()
        self.cable_tab = CableTab()
        self.selection_tab = SelectionTab()
        self.layer_tab = LayerTab(self.settings)

        self.accordion = Accordion()
        specs = (
            ("⦿", "Source & Delimiter", self.delimiter_tab),
            ("✎", "Drawing Mode", self.draw_tab),
            ("○", "Points", self.points_tab),
            ("☰", "Heights", self.heights_tab),
            ("╱", "Cable Marks", self.cable_tab),
            ("▢", "Selection", self.selection_tab),
            ("▤", "Layer", self.layer_tab),
        )
        for icon, title, tab in specs:
            section = AccordionSection(icon, title, tab)
            self.accordion.add_section(section)
            self._sections.append((section, tab))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.accordion)
        outer.addWidget(scroll, 1)

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

        self.draw_tab.mode_changed.connect(self._on_config_changed)
        self.points_tab.numbers_toggled.connect(self._on_config_changed)
        self.points_tab.option_changed.connect(self._on_config_changed)
        self.heights_tab.option_changed.connect(self._on_config_changed)
        self.cable_tab.option_changed.connect(self._on_config_changed)
        self.selection_tab.selection_changed.connect(self._on_config_changed)
        self.layer_tab.layer_changed.connect(self._on_config_changed)

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

    def _on_delimiter_changed(self) -> None:
        if self.file_path:
            self._reparse_current_file()
        self._on_config_changed()

    # ==================================================================
    # RENDERING
    # ==================================================================
    def _refresh(self) -> None:
        state = self._current_state()

        if state is AppState.EMPTY:
            self.file_stack.setCurrentWidget(self.drop_zone)
            self.accordion.setEnabled(False)
            self.error_banner.clear()
            self.stepper.set_step(0)
            file_label = "No file selected"
            layer_text = "Layer: –"
            delim_text = "Delimiter: –"
        else:
            name, count, size = os.path.basename(self.file_path), len(self.data), self.file_size_text
            self.file_card.set_file(name, count, size)
            self.file_stack.setCurrentWidget(self.file_card)
            self.accordion.setEnabled(True)
            file_label = f"{name} · {count} points"
            layer_text = f"Layer: {self.layer_tab.get_layer_name() or '0'}"
            delim_text = f"Delimiter: {self._delimiter_display_name()}"

            if state is AppState.READY:
                self.error_banner.clear()
                self.stepper.set_step(2)
            elif state is AppState.APPLIED:
                self.error_banner.clear()
                self.stepper.set_step(3)
            else:  # ERROR
                self.error_banner.show_message(self._last_error)
                self.stepper.set_step(2, error=True)

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
    def _build_generation_config(self, layer_name: str) -> GenerationConfig:
        return GenerationConfig(
            layer_name=layer_name,
            draw_mode=self.draw_tab.draw_mode,
            cabinet_mode=self.delimiter_tab.cabinet_mode_enabled,
            points=self.points_tab.get_options(),
            heights=self.heights_tab.get_options(),
            cable=self.cable_tab.get_options(),
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
            layer_name = resolve_layer_name(self.layer_tab.get_layer_name())
            selected_numbers = self.selection_tab.get_selected_numbers(self.data)
            ensure_selection(selected_numbers)
            config = self._build_generation_config(layer_name)
            command = self.survey_draw_service.build_command(self.data, selected_numbers, config)
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
