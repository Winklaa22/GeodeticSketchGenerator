import math
import os
from dataclasses import dataclass
from typing import Dict, Tuple, List

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QSplitter,
    QToolBar,
    QStatusBar,
)


@dataclass
class Point:
    x: float
    y: float
    h: float


class AutoCADScriptGeneratorPro(QMainWindow):
    """
    A polished, more user-friendly version of the original AutoCAD script generator.
    - Cleaner layout using QMainWindow, toolbar, tabs, and splitter.
    - Validators for numeric inputs.
    - Auto-detects delimiter (space/tab) with manual override.
    - Keeps original behavior: X<->Y swap (geodetic), multiple drawing modes, selections, and options.
    - Adds: Copy/Save script actions, persistent settings, and nicer defaults.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoCAD Script Generator PRO")
        self.resize(980, 720)
        self.settings = QtCore.QSettings("acsg", "acsg_pro")

        # STATE
        self.file_path: str = ""
        self.data: Dict[int, Point] = {}

        # --- UI ---
        self._build_toolbar()
        self._build_central()
        self._restore_settings()
        self._apply_style()

    # -------------------- UI BUILDERS --------------------
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)

        act_open = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon), "Open", self)
        act_open.triggered.connect(self.select_file)
        tb.addAction(act_open)

        act_generate = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay), "Generate", self)
        act_generate.triggered.connect(self.generate_script)
        tb.addAction(act_generate)

        act_copy = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogYesButton), "Copy", self)
        act_copy.triggered.connect(self.copy_script)
        tb.addAction(act_copy)

        act_save = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton), "Save .scr", self)
        act_save.triggered.connect(self.save_script)
        tb.addAction(act_save)

        tb.addSeparator()
        self.live_preview_chk = QCheckBox("Live preview")
        self.live_preview_chk.setChecked(True)
        self.live_preview_chk.toggled.connect(self._maybe_generate)
        tb.addWidget(self.live_preview_chk)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Vertical)

        # --- Top area: inputs ---
        top = QWidget()
        top_layout = QVBoxLayout(top)

        # File row
        file_row = QHBoxLayout()
        self.file_btn = QPushButton("Select input TXT file")
        self.file_btn.clicked.connect(self.select_file)
        self.file_label = QLabel("No file selected")
        self.file_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        file_row.addWidget(self.file_btn)
        file_row.addWidget(self.file_label, 1)
        top_layout.addLayout(file_row)

        # Tabs for options
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_delimiter(), "Delimiter & Source")
        self.tabs.addTab(self._tab_draw(), "Drawing")
        self.tabs.addTab(self._tab_points(), "Points")
        self.tabs.addTab(self._tab_heights(), "Heights")
        self.tabs.addTab(self._tab_cable(), "Cable marks")
        self.tabs.addTab(self._tab_selection(), "Selection")
        self.tabs.addTab(self._tab_layer(), "Layer")
        self.tabs.currentChanged.connect(self._maybe_generate)
        top_layout.addWidget(self.tabs)

        top_box = QWidget()
        top_box.setLayout(top_layout)

        # --- Bottom area: output ---
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)

        self.generate_btn = QPushButton("Generate Script")
        self.generate_btn.clicked.connect(self.generate_script)
        bottom_layout.addWidget(self.generate_btn)

        self.output = QPlainTextEdit()
        self.output.setPlaceholderText("Script output will appear here…")
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        bottom_layout.addWidget(self.output, 1)

        splitter.addWidget(top_box)
        splitter.addWidget(bottom)
        splitter.setSizes([420, 300])

        root_layout = QVBoxLayout(central)
        root_layout.addWidget(splitter)

    # ---- Tabs ----
    def _tab_delimiter(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)

        # Gap type group
        gap_box = QGroupBox("Gap type")
        hb = QHBoxLayout()
        self.space_radio = QRadioButton("Space")
        self.tab_radio = QRadioButton("Tab")
        self.auto_radio = QRadioButton("Auto-detect")
        self.auto_radio.setChecked(True)
        hb.addWidget(self.auto_radio)
        hb.addWidget(self.space_radio)
        hb.addWidget(self.tab_radio)
        gap_box.setLayout(hb)
        lay.addRow(gap_box)

        # Swap XY
        self.swap_xy_chk = QCheckBox("Swap X ↔ Y (geodetic)")
        self.swap_xy_chk.setChecked(True)
        self.swap_xy_chk.toggled.connect(self._maybe_generate)
        lay.addRow(self.swap_xy_chk)

        # Cabinet
        self.cabinet_radio = QCheckBox("Cabinet mode (shrink last 6 labels)")
        self.cabinet_radio.setChecked(False)
        self.cabinet_radio.toggled.connect(self._maybe_generate)
        lay.addRow(self.cabinet_radio)

        return w

    def _tab_draw(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        group = QGroupBox("Drawing option")
        hb = QHBoxLayout()
        self.points_radio = QRadioButton("Points")
        self.lines_radio = QRadioButton("Lines")
        self.pline_radio = QRadioButton("PLines")
        self.poly3d_radio = QRadioButton("3DPOLY")
        self.heights_radio = QRadioButton("Heights marks")
        self.cable_radio = QRadioButton("Cable marks")
        self.points_radio.toggled.connect(self._toggle_extra)
        self.heights_radio.toggled.connect(self._toggle_extra)
        self.cable_radio.toggled.connect(self._toggle_extra)
        hb.addWidget(self.points_radio)
        hb.addWidget(self.lines_radio)
        hb.addWidget(self.pline_radio)
        hb.addWidget(self.poly3d_radio)
        hb.addWidget(self.heights_radio)
        hb.addWidget(self.cable_radio)
        group.setLayout(hb)
        lay.addWidget(group)

        return w

    def _tab_points(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)

        self.numbers_checkbox = QCheckBox("Add numbers to points")
        self.numbers_checkbox.stateChanged.connect(self._toggle_font_size)
        lay.addRow(self.numbers_checkbox)

        self.points_font_size_input = QLineEdit("0.6")
        self.points_font_size_input.setPlaceholderText("Text size, e.g. 0.6")
        self.points_font_size_input.setValidator(QtGui.QDoubleValidator(0.0, 9999.0, 3))
        self.points_font_size_input.hide()
        lay.addRow("Text size", self.points_font_size_input)

        self.diameter_input = QLineEdit("0.05")
        self.diameter_input.setPlaceholderText("Circle diameter, e.g. 0.05")
        self.diameter_input.setValidator(QtGui.QDoubleValidator(0.0, 9999.0, 3))
        lay.addRow("Circle diameter", self.diameter_input)

        return w

    def _tab_heights(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        self.heights_font_size_input = QLineEdit("0.6")
        self.heights_font_size_input.setValidator(QtGui.QDoubleValidator(0.0, 9999.0, 3))
        self.heights_frequency_input = QLineEdit("5")
        self.heights_frequency_input.setValidator(QtGui.QIntValidator(1, 10**6))
        lay.addRow("Text size", self.heights_font_size_input)
        lay.addRow("Frequency (every Nth point)", self.heights_frequency_input)
        return w

    def _tab_cable(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        self.cable_marks_font_size_input = QLineEdit("0.6")
        self.cable_marks_font_size_input.setValidator(QtGui.QDoubleValidator(0.0, 9999.0, 3))
        self.cable_marks_frequency_input = QLineEdit("5")
        self.cable_marks_frequency_input.setValidator(QtGui.QIntValidator(1, 10**6))
        self.cable_marks_font_text_input = QLineEdit("eN")
        lay.addRow("Text size", self.cable_marks_font_size_input)
        lay.addRow("Frequency (every Nth segment)", self.cable_marks_frequency_input)
        lay.addRow("Marks text", self.cable_marks_font_text_input)
        return w

    def _tab_selection(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        group = QGroupBox("Select points")
        hb = QHBoxLayout()
        self.all_radio = QRadioButton("All points")
        self.separate_radio = QRadioButton("Separately…")
        self.range_radio = QRadioButton("In range…")
        self.all_radio.setChecked(True)
        hb.addWidget(self.all_radio)
        hb.addWidget(self.separate_radio)
        hb.addWidget(self.range_radio)
        group.setLayout(hb)
        lay.addWidget(group)

        return w

    def _tab_layer(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        self.layer_input = QLineEdit(self.settings.value("layer", "0"))
        self.layer_input.setPlaceholderText("Enter layer name")
        lay.addRow("Layer", self.layer_input)
        return w

    # -------------------- STYLE --------------------
    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow { background: #0b0c0e; }
            QWidget { color: #e5e7eb; font-size: 13px; }
            QGroupBox { background-color: #1f2937;  border: 1px solid #27272a; border-radius: 10px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #a1a1aa; }
            QLabel { color: #e5e7eb; }
            QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 6px; color: #e5e7eb; }
            QPushButton { background: #16a34a; border: none; border-radius: 10px; padding: 8px 12px; color: white; font-weight: 600; }
            QPushButton:hover { background: #22c55e; }
            QPushButton:disabled { background: #374151; color: #9ca3af; }
            QTabBar::tab { background: #111827; padding: 6px 10px; border-top-left-radius: 8px; border-top-right-radius: 8px; color: #d1d5db; }
            QTabBar::tab:selected { background: #1f2937; }
            QStatusBar { color: #94a3b8; }
            """
        )

    # -------------------- HELPERS --------------------
    def _save_settings(self):
        self.settings.setValue("layer", self.layer_input.text())

    def _restore_settings(self):
        pass

    def _maybe_generate(self):
        if self.live_preview_chk.isChecked():
            self.generate_script()

    def _toggle_extra(self):
        # just triggers preview refresh; the dedicated tabs are always visible
        self._maybe_generate()

    def _toggle_font_size(self):
        self.points_font_size_input.setVisible(self.numbers_checkbox.isChecked())
        self._maybe_generate()

    # -------------------- IO --------------------
    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open TXT File", "", "Text Files (*.txt)")
        if file_path:
            self.file_path = file_path
            self.file_label.setText(file_path)
            try:
                self._load_data(file_path)
                self.status.showMessage(f"Loaded {len(self.data)} points", 5000)
                self._maybe_generate()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # -------------------- PARSING --------------------
    def _detect_delimiter(self, sample_line: str) -> str:
        # Prefer TAB if present, else space
        if "\t" in sample_line:
            return "\t"
        return " "

    def _load_data(self, file_path: str):
        if not os.path.isfile(file_path):
            raise FileNotFoundError("No valid input file selected.")
        self.data.clear()
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            raise ValueError("Input file is empty.")

        # decide delimiter
        if self.auto_radio.isChecked():
            gap = self._detect_delimiter(lines[0])
        elif self.space_radio.isChecked():
            gap = " "
        else:
            gap = "\t"

        # skip header if looks like one
        start_idx = 1 if any(h in lines[0].lower() for h in ("numer", "x", "y")) else 0

        for line in lines[start_idx:]:
            parts = [p for p in line.replace(",", ".").split(gap) if p != ""]
            if len(parts) < 3:
                # Try fallback: split on any whitespace
                parts = [p for p in line.replace(",", ".").split() if p != ""]
                if len(parts) < 3:
                    continue
            try:
                number = int(parts[0])
            except ValueError:
                # non-integer numbering? skip row
                continue

            # Original code: read X from column 2, Y from column 1, H from column 3 (if any)
            # And SWAP X<->Y for geodetic
            file_x = float(parts[1]) if len(parts) > 1 else 0.0
            file_y = float(parts[2]) if len(parts) > 2 else 0.0
            file_h = float(parts[3]) if len(parts) > 3 else 0.0
            # swap X<->Y
            x = file_y
            y = file_x
            self.data[number] = Point(x=x, y=y, h=file_h)

        if not self.data:
            raise ValueError("No valid point rows parsed.")

    # -------------------- SCRIPT GEN --------------------
    def generate_script(self):
        try:
            self._save_settings()

            if not self.data and not self.file_path:
                QMessageBox.critical(self, "Error", "No valid input file selected.")
                return

            layer_name = (self.layer_input.text() or "0").strip()
            if not layer_name:
                QMessageBox.critical(self, "Error", "Please enter layer name.")
                return

            # drawing option
            draw_option = (
                1 if self.points_radio.isChecked() else
                2 if self.lines_radio.isChecked() else
                3 if self.pline_radio.isChecked() else
                4 if self.poly3d_radio.isChecked() else
                5 if self.heights_radio.isChecked() else 6
            )

            # Selections
            select_points = self._get_selection()
            if not select_points:
                QMessageBox.critical(self, "Error", "No points selected.")
                return

            # Options
            if draw_option == 1:
                if_text_points = self.numbers_checkbox.isChecked()
                font_size = float(self.points_font_size_input.text() or 0.6) if if_text_points else 0.2
                diameter = float((self.diameter_input.text() or "0.1").replace(",", "."))
                radius = max(diameter / 2.0, 0.0)
            elif draw_option == 5:
                font_size = float(self.heights_font_size_input.text() or 0.6)
                frequency = int(self.heights_frequency_input.text() or 5)
            elif draw_option == 6:
                font_size = float(self.cable_marks_font_size_input.text() or 0.6)
                frequency = int(self.cable_marks_frequency_input.text() or 5)
                cable_marks_text = (self.cable_marks_font_text_input.text() or "eN")
            else:
                if_text_points = False
                font_size = 0.2
                cable_marks_text = "eN"
                radius = 0.0
                frequency = 1

            # Generating output
            output = [f"-LAYER", f"MAKE {layer_name}", ""]
            if draw_option == 2:
                output.append("LINE")
            elif draw_option == 3:
                output.append("PLINE")
            elif draw_option == 4:
                output.append("3DPOLY")

            angle_deg = 0.0
            last_idx = max(select_points) if select_points else 0
            selected_set = set(select_points)

            for number in select_points:
                pt = self.data.get(number)
                if not pt:
                    continue
                x, y, h = pt.x, pt.y, pt.h
                rot = 0.0
                if number < last_idx and (number + 1) in self.data:
                    x2, y2, _ = self.data[number + 1].x, self.data[number + 1].y, self.data[number + 1].h
                    dx = float(x2) - float(x)
                    dy = float(y2) - float(y)
                    if dx == 0 and dy == 0:
                        angle_deg = 0
                    else:
                        angle_rad = math.atan2(dy, dx)
                        angle_deg = math.degrees(angle_rad)
                        if angle_deg < 0:
                            angle_deg += 360
                        if 90 < angle_deg < 270:
                            angle_deg += 180
                            if angle_deg >= 360:
                                angle_deg -= 360
                rot = round(angle_deg, 1)

                if draw_option == 1:  # Points
                    output.append(f"CIRCLE {x},{y},{h} {radius}")
                    if if_text_points:
                        parameter_space = float(font_size) / 2.0
                        x_space = 0.0
                        y_space = 0.0
                        if 45 <= angle_deg < 135:
                            y_space -= parameter_space
                            x_space += parameter_space
                        elif 135 <= angle_deg < 225:
                            y_space += parameter_space
                            x_space -= parameter_space
                        elif 225 <= angle_deg < 315:
                            y_space -= parameter_space
                            x_space -= parameter_space
                        else:
                            y_space += parameter_space
                            x_space -= parameter_space

                        size = font_size
                        # cabinet mode: shrink labels for last 6 points
                        if self.cabinet_radio.isChecked() and number in sorted(selected_set)[-6:]:
                            size = float(font_size) / 2.0
                            x_space = 0.0
                            y_space = 0.0

                        output.append(f"-TEXT {x + x_space},{y + y_space},{h} {size} 0 {number}")

                elif draw_option == 3:  # PLINE
                    output.append(f"{x},{y}")

                elif draw_option == 5:  # Heights marks
                    x_space = 0.0
                    y_space = 0.0
                    if 45 <= angle_deg < 135:
                        y_space += 0.5
                        x_space += (float(font_size) / 2.0)
                    elif 135 <= angle_deg < 225:
                        x_space -= 0.5
                        y_space += (float(font_size) / 2.0)
                    elif 225 <= angle_deg < 315:
                        y_space -= 0.5
                        x_space -= (float(font_size) / 2.0)
                    else:
                        x_space += 0.5
                        y_space -= (float(font_size) / 2.0)

                    if 0 <= angle_deg < 20:
                        rot = 0

                    if number % frequency == 0:
                        rounded_height = (math.ceil(float(h) * 10) / 10)
                        output.append(f"-TEXT {x + x_space},{y + y_space},{h} {font_size} {rot} {rounded_height}")

                elif draw_option == 6:  # Cable marks
                    if number < last_idx and (number + 1) in self.data:
                        x2, y2, _ = self.data[number + 1].x, self.data[number + 1].y, self.data[number + 1].h
                        x_mid = (float(x) + float(x2)) / 2.0
                        y_mid = (float(y) + float(y2)) / 2.0

                        x_space = 0.0
                        y_space = 0.0
                        if 45 <= angle_deg < 135:
                            x_space += (float(font_size) / 2.0)
                        elif 135 <= angle_deg < 225:
                            y_space += (float(font_size) / 2.0)
                        elif 225 <= angle_deg < 315:
                            x_space -= (float(font_size) / 2.0)
                        else:
                            y_space -= (float(font_size) / 2.0)

                        if 0 <= angle_deg < 20:
                            rot = 0

                        if number % frequency == 0:
                            output.append(f"-TEXT {x_mid + x_space},{y_mid + y_space},{h} {font_size} {rot} {cable_marks_text}")

                else:  # Lines / 3DPOLY default point list
                    output.append(f"{x},{y},{h}")

            self.output.setPlainText("\n".join(output))
            self.status.showMessage("Script generated", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _get_selection(self) -> List[int]:
        if self.separate_radio.isChecked():
            select_str, ok = QtWidgets.QInputDialog.getText(self, "Select Points", "Enter points (e.g. 1,2,3):")
            if not ok:
                return []
            return [int(x.strip()) for x in select_str.split(",") if x.strip().isdigit()]
        elif self.range_radio.isChecked():
            range_str, ok = QtWidgets.QInputDialog.getText(self, "Select Range", "Enter range (e.g. 1-7):")
            if not ok:
                return []
            try:
                start, end = [int(x.strip()) for x in range_str.split("-")]
            except Exception:
                return []
            return list(range(min(start, end), max(start, end) + 1))
        else:
            return sorted(self.data.keys())

    # -------------------- UTIL --------------------
    def copy_script(self):
        text = self.output.toPlainText().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.showMessage("Copied to clipboard", 3000)

    def save_script(self):
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Save .scr", "Nothing to save. Generate a script first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Script", "geodata.scr", "AutoCAD Script (*.scr)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.status.showMessage(f"Saved to {path}", 5000)


# -------------------- Simple tests for parsing & swap --------------------
def _run_tests():
    def parse_fake(lines: List[str], use_tab=False):
        # helper mimicking _load_data core logic
        data: Dict[int, Point] = {}
        gap = "\t" if use_tab else " "
        start_idx = 1 if any(h in lines[0].lower() for h in ("numer", "x", "y")) else 0
        for line in lines[start_idx:]:
            parts = [p for p in line.replace(",", ".").split(gap) if p]
            if len(parts) < 3:
                parts = line.replace(",", ".").split()
                if len(parts) < 3:
                    continue
            try:
                number = int(parts[0])
            except ValueError:
                continue
            fx = float(parts[1]); fy = float(parts[2]); fh = float(parts[3]) if len(parts) > 3 else 0.0
            data[number] = Point(x=fy, y=fx, h=fh)  # swap
        return data

    tests = []

    # 1) header + swap
    d = parse_fake(["Numer X Y H", "1 100 200 5", "2 110 210 6"])
    tests.append(("header+swap", d.get(1).x == 200 and d.get(1).y == 100 and d.get(2).x == 210))

    # 2) no header
    d = parse_fake(["1 100 200 5", "2 110 210 6"])
    tests.append(("no header", len(d) == 2))

    # 3) commas
    d = parse_fake(["Numer X Y", "3 100,5 200,25"])
    tests.append(("comma decimals", abs(d.get(3).x - 200.25) < 1e-9 and abs(d.get(3).y - 100.5) < 1e-9))

    # 4) tabs
    d = parse_fake(["Numer\tX\tY\tH", "1\t100\t200\t5"], use_tab=True)
    tests.append(("tab delimiter", d.get(1).x == 200))

    # 5) skip bad rows
    d = parse_fake(["Numer X Y", "A 10 20", "4 30 40"])
    tests.append(("skip bad", (1 not in d) and (4 in d)))

    ok = all(flag for _, flag in tests)
    return ok, tests


if __name__ == "__main__":
    # Optional quick test log
    ok, tests = _run_tests()
    print("TESTS:")
    for name, flag in tests:
        print(f" - {name}: {'OK' if flag else 'FAIL'}")

    app = QApplication([])
    win = AutoCADScriptGeneratorPro()
    win.show()
    app.exec()
