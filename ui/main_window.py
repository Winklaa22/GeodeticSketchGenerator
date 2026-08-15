from __future__ import annotations

import os
from enum import Enum
from typing import Dict, List, Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
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
from core.script_generator import ScriptGenerator
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point
from ui.fixtures import (
    DEMO_ERROR_MESSAGE,
    DEMO_FILE_NAME,
    DEMO_FILE_SIZE,
    DEMO_POINTS_COUNT,
    DEMO_SCRIPT_TEXT,
)
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
    CheckField,
    ConsoleView,
    DropZone,
    ErrorBanner,
    FileCard,
    SegmentedControl,
    Tag,
    WorkflowStepper,
    restyle,
)

_DELIMITER_DISPLAY = {"auto": "Auto", "space": "Space", "tab": "Tab"}
_STATUS_TEXT = {
    "empty": "Empty",
    "ready": "Ready",
    "generated": "Generated",
    "error": "Errors: 1",
}


class DemoState(Enum):
    """The four shell states the top-bar switcher can preview."""

    EMPTY = "empty"
    READY = "ready"
    GENERATED = "generated"
    ERROR = "error"


class MainWindow(QMainWindow):

    STEP_NAMES = ("Load file", "Configure", "Preview", "Export")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoCAD Script Generator PRO")
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)
        self.settings = QtCore.QSettings("acsg", "acsg_pro")

        self.parser = PointFileParser()
        self.script_generator = ScriptGenerator()

        self.file_path: str = ""
        self.file_size_text: str = ""
        self.data: Dict[int, Point] = {}
        self._last_script_text: str = ""
        self._displayed_script_text: str = ""
        self._has_generated = False
        self._last_error: Optional[str] = None
        # None => the switcher follows real app state; a value => the user
        # pinned it to preview that state with sample data.
        self._demo_override: Optional[DemoState] = None
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

        title = QLabel('AutoCAD Script Generator <span style="color:#9184d9;">PRO</span>')
        title.setObjectName("appTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        version_tag = Tag("v3.2", variant="neutral")

        layout.addWidget(title)
        layout.addWidget(version_tag)
        layout.addStretch(1)

        demo_label = QLabel("DEMO STATE")
        demo_label.setObjectName("demoStateLabel")
        self.demo_switch = SegmentedControl(
            [("ready", "Ready"), ("generated", "Generated"), ("error", "Error")]
        )
        self.demo_switch.currentChanged.connect(self._on_demo_state_selected)

        layout.addWidget(demo_label)
        layout.addWidget(self.demo_switch)
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
        title = QLabel("Script preview")
        title.setObjectName("previewHeaderTitle")
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("previewMeta")
        header.addWidget(title)
        header.addWidget(self.preview_meta)
        header.addStretch(1)
        self.live_preview_checkbox = CheckField("Live preview")
        self.live_preview_checkbox.setChecked(True)
        header.addWidget(self.live_preview_checkbox)
        layout.addLayout(header)

        self.error_banner = ErrorBanner()
        layout.addWidget(self.error_banner)

        self.console = ConsoleView()
        layout.addWidget(self.console, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(SPACE_SM)
        self.copy_button = self._make_button("Copy", "secondary", self.copy_script)
        self.save_button = self._make_button("Save as .scr", "secondary", self.save_script)
        self.generate_button = self._make_button("Generate Script  →", "primary", self.generate_script)
        button_row.addWidget(self.copy_button)
        button_row.addWidget(self.save_button)
        button_row.addStretch(1)
        button_row.addWidget(self.generate_button)
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
        self.live_preview_checkbox.toggled.connect(self._on_config_changed)

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

    # ==================================================================
    # STATE
    # ==================================================================
    def _current_real_state(self) -> DemoState:
        if self._last_error:
            return DemoState.ERROR
        if not self.file_path:
            return DemoState.EMPTY
        if self._has_generated:
            return DemoState.GENERATED
        return DemoState.READY

    def _effective_state(self) -> DemoState:
        return self._demo_override if self._demo_override is not None else self._current_real_state()

    def _on_demo_state_selected(self, key: str) -> None:
        self._demo_override = DemoState(key)
        self._refresh()

    def _on_config_changed(self, *_args) -> None:
        self._refresh_modified_dots()
        self._maybe_generate()

    def _on_delimiter_changed(self) -> None:
        if self.file_path:
            self._reparse_current_file()
        self._on_config_changed()

    # ==================================================================
    # RENDERING
    # ==================================================================
    def _refresh(self) -> None:
        state = self._effective_state()
        # The switcher only ever previews states reachable from a real,
        # already-loaded file — never fabricated ones for an empty start.
        has_file = bool(self.file_path)
        for key in ("ready", "generated", "error"):
            self.demo_switch.setButtonEnabled(key, has_file)

        if state is DemoState.EMPTY:
            # "Ready" reads as the switcher's natural resting default (like
            # any other option group in this app); it stays disabled above
            # until a real file exists, so this is a look, not a preview.
            self.demo_switch.setCurrent("ready")
            self.file_stack.setCurrentWidget(self.drop_zone)
            self.accordion.setEnabled(False)
            self.error_banner.clear()
            self.console.show_empty()
            self.stepper.set_step(0)
            file_label = "No file selected"
            layer_text = "Layer: –"
            delim_text = "Delimiter: –"
            self._displayed_script_text = ""
        else:
            self.demo_switch.setCurrent(state.value)
            name, count, size = self._file_card_data()
            self.file_card.set_file(name, count, size)
            self.file_stack.setCurrentWidget(self.file_card)
            self.accordion.setEnabled(True)
            file_label = f"{name} · {count} points"
            layer_text = f"Layer: {self.layer_tab.get_layer_name() or '0'}"
            delim_text = f"Delimiter: {self._delimiter_display_name()}"

            if state is DemoState.READY:
                self.error_banner.clear()
                self.console.show_empty()
                self.stepper.set_step(2)
                self._displayed_script_text = ""
            elif state is DemoState.GENERATED:
                self.error_banner.clear()
                self._displayed_script_text = self._script_text_for_display()
                self.console.set_script(self._displayed_script_text)
                self.stepper.set_step(3)
            else:  # ERROR
                self.error_banner.show_message(self._last_error or DEMO_ERROR_MESSAGE)
                self.console.show_empty()
                self.stepper.set_step(2, error=True)
                self._displayed_script_text = ""

        self.status_file_label.setText(file_label)
        self.status_layer_label.setText(layer_text)
        self.status_delim_label.setText(delim_text)
        self.status_state_label.setText(_STATUS_TEXT[state.value])
        self.status_state_label.setProperty("variant", "error" if state is DemoState.ERROR else "normal")
        restyle(self.status_state_label)

        self.copy_button.setEnabled(bool(self._displayed_script_text))
        self.save_button.setEnabled(bool(self._displayed_script_text))
        self.generate_button.setEnabled(state is not DemoState.EMPTY)

        self._update_preview_meta(state)
        self._refresh_modified_dots()

    def _file_card_data(self) -> Tuple[str, int, str]:
        if self.file_path:
            return os.path.basename(self.file_path), len(self.data), self.file_size_text
        return DEMO_FILE_NAME, DEMO_POINTS_COUNT, DEMO_FILE_SIZE

    def _script_text_for_display(self) -> str:
        if self.file_path and self._has_generated and self._last_script_text:
            return self._last_script_text
        return DEMO_SCRIPT_TEXT

    def _update_preview_meta(self, state: DemoState) -> None:
        if state is not DemoState.GENERATED:
            self.preview_meta.setText("")
            return
        text = self._script_text_for_display()
        lines = len(text.splitlines())
        count = len(self.data) if (self.file_path and self.data) else DEMO_POINTS_COUNT
        self.preview_meta.setText(f"{lines} lines · {count} points")

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
    def _maybe_generate(self) -> None:
        if self.live_preview_checkbox.isChecked() and self.file_path and self.data:
            self.generate_script()

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
        self._demo_override = None
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
            self._has_generated = False
            self._refresh()
            return
        self._has_generated = False
        self._last_error = None
        self._refresh()
        self._maybe_generate()

    def _reparse_current_file(self) -> None:
        try:
            self.data = self.parser.parse_file(self.file_path, self.delimiter_tab.delimiter_mode)
            self._last_error = None
        except AppError as exc:
            self.data = {}
            self._last_error = str(exc)
        self._has_generated = False

    # ==================================================================
    # SCRIPT GENERATION
    # ==================================================================
    def generate_script(self) -> None:
        self.layer_tab.persist(self.settings)
        self._demo_override = None
        try:
            ensure_has_data(self.data, self.file_path)
            layer_name = resolve_layer_name(self.layer_tab.get_layer_name())
            selected_numbers = self.selection_tab.get_selected_numbers(self.data)
            ensure_selection(selected_numbers)
            config = self._build_generation_config(layer_name)
            script_text = self.script_generator.generate(self.data, selected_numbers, config)
        except AppError as exc:
            self._last_error = str(exc)
            self._has_generated = False
            self._refresh()
            return
        self._last_error = None
        self._has_generated = True
        self._last_script_text = script_text
        self._refresh()

    # ==================================================================
    # UTIL
    # ==================================================================
    def copy_script(self) -> None:
        if not self._displayed_script_text:
            return
        QApplication.clipboard().setText(self._displayed_script_text)
        self._flash_status("Copied to clipboard")

    def save_script(self) -> None:
        if not self._displayed_script_text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Script", "geodata.scr", "AutoCAD Script (*.scr)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._displayed_script_text)
        self._flash_status(f"Saved to {os.path.basename(path)}")
