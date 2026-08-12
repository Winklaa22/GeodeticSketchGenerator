from __future__ import annotations

from typing import Dict

from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.config import GenerationConfig
from core.exceptions import AppError
from core.parser import PointFileParser
from core.script_generator import ScriptGenerator
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point
from ui.style import APP_STYLESHEET
from ui.tabs.cable_tab import CableTab
from ui.tabs.delimiter_tab import DelimiterTab
from ui.tabs.draw_tab import DrawTab
from ui.tabs.heights_tab import HeightsTab
from ui.tabs.layer_tab import LayerTab
from ui.tabs.points_tab import PointsTab
from ui.tabs.selection_tab import SelectionTab


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoCAD Script Generator PRO")
        self.resize(980, 720)
        self.settings = QtCore.QSettings("acsg", "acsg_pro")

        self.parser = PointFileParser()
        self.script_generator = ScriptGenerator()

        self.file_path: str = ""
        self.data: Dict[int, Point] = {}

        self._build_toolbar()
        self._build_central()
        self._wire_live_preview()
        self.setStyleSheet(APP_STYLESHEET)

    # -------------------- UI BUILDERS --------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(toolbar)
        style = self.style()

        open_action = QtGui.QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "Open", self)
        open_action.triggered.connect(self.select_file)
        toolbar.addAction(open_action)

        generate_action = QtGui.QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Generate", self)
        generate_action.triggered.connect(self.generate_script)
        toolbar.addAction(generate_action)

        copy_action = QtGui.QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton), "Copy", self)
        copy_action.triggered.connect(self.copy_script)
        toolbar.addAction(copy_action)

        save_action = QtGui.QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Save .scr", self)
        save_action.triggered.connect(self.save_script)
        toolbar.addAction(save_action)

        toolbar.addSeparator()
        self.live_preview_checkbox = QCheckBox("Live preview")
        self.live_preview_checkbox.setChecked(True)
        toolbar.addWidget(self.live_preview_checkbox)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Vertical)

        top = QWidget()
        top_layout = QVBoxLayout(top)

        file_row = QHBoxLayout()
        self.file_button = QPushButton("Select input TXT file")
        self.file_button.clicked.connect(self.select_file)
        self.file_label = QLabel("No file selected")
        self.file_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        file_row.addWidget(self.file_button)
        file_row.addWidget(self.file_label, 1)
        top_layout.addLayout(file_row)

        self.tabs = QTabWidget()
        self.delimiter_tab = DelimiterTab()
        self.draw_tab = DrawTab()
        self.points_tab = PointsTab()
        self.heights_tab = HeightsTab()
        self.cable_tab = CableTab()
        self.selection_tab = SelectionTab()
        self.layer_tab = LayerTab(self.settings)
        self.tabs.addTab(self.delimiter_tab, "Delimiter & Source")
        self.tabs.addTab(self.draw_tab, "Drawing")
        self.tabs.addTab(self.points_tab, "Points")
        self.tabs.addTab(self.heights_tab, "Heights")
        self.tabs.addTab(self.cable_tab, "Cable marks")
        self.tabs.addTab(self.selection_tab, "Selection")
        self.tabs.addTab(self.layer_tab, "Layer")
        top_layout.addWidget(self.tabs)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)

        self.generate_button = QPushButton("Generate Script")
        self.generate_button.clicked.connect(self.generate_script)
        bottom_layout.addWidget(self.generate_button)

        self.output = QPlainTextEdit()
        self.output.setPlaceholderText("Script output will appear here…")
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        bottom_layout.addWidget(self.output, 1)

        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setSizes([420, 300])

        root_layout = QVBoxLayout(central)
        root_layout.addWidget(splitter)

    def _wire_live_preview(self) -> None:

        self.live_preview_checkbox.toggled.connect(self._maybe_generate)
        self.tabs.currentChanged.connect(self._maybe_generate)
        self.delimiter_tab.swap_xy_toggled.connect(self._maybe_generate)
        self.delimiter_tab.cabinet_mode_toggled.connect(self._maybe_generate)
        self.draw_tab.preview_relevant_toggled.connect(self._maybe_generate)
        self.points_tab.numbers_toggled.connect(self._maybe_generate)

    # -------------------- HELPERS --------------------
    def _maybe_generate(self) -> None:
        if self.live_preview_checkbox.isChecked() and self.file_path:
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

    # -------------------- IO --------------------
    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open TXT File", "", "Text Files (*.txt)")
        if not file_path:
            return
        self.file_path = file_path
        self.file_label.setText(file_path)
        try:
            self.data = self.parser.parse_file(file_path, self.delimiter_tab.delimiter_mode)
        except AppError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.status.showMessage(f"Loaded {len(self.data)} points", 5000)
        self._maybe_generate()

    # -------------------- SCRIPT GENERATION --------------------
    def generate_script(self) -> None:
        self.layer_tab.persist(self.settings)
        try:
            ensure_has_data(self.data, self.file_path)
            layer_name = resolve_layer_name(self.layer_tab.get_layer_name())
            selected_numbers = self.selection_tab.get_selected_numbers(self.data)
            ensure_selection(selected_numbers)
            config = self._build_generation_config(layer_name)
            script_text = self.script_generator.generate(self.data, selected_numbers, config)
        except AppError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.output.setPlainText(script_text)
        self.status.showMessage("Script generated", 3000)

    # -------------------- UTIL --------------------
    def copy_script(self) -> None:
        text = self.output.toPlainText().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.showMessage("Copied to clipboard", 3000)

    def save_script(self) -> None:
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Save .scr", "Nothing to save. Generate a script first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Script", "geodata.scr", "AutoCAD Script (*.scr)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.status.showMessage(f"Saved to {path}", 5000)
