import os
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import QFileDialog, QMessageBox

class AutoCADScriptGenerator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("AutoCAD Script Generator")
        self.setGeometry(200, 200, 700, 700)

        layout = QtWidgets.QVBoxLayout()

        # File selection
        self.file_path_btn = QtWidgets.QPushButton("Select input TXT file")
        self.file_path_btn.clicked.connect(self.select_file)
        self.file_path_label = QtWidgets.QLabel("No file selected")
        layout.addWidget(self.file_path_btn)
        layout.addWidget(self.file_path_label)

        # Gap type
        self.gap_group = QtWidgets.QGroupBox("Select gap type:")
        self.space_radio = QtWidgets.QRadioButton("Space")
        self.tab_radio = QtWidgets.QRadioButton("Tab")
        self.space_radio.setChecked(True)
        gap_layout = QtWidgets.QHBoxLayout()
        gap_layout.addWidget(self.space_radio)
        gap_layout.addWidget(self.tab_radio)
        self.gap_group.setLayout(gap_layout)
        layout.addWidget(self.gap_group)

        # Drawing option
        self.draw_group = QtWidgets.QGroupBox("Select drawing option:")
        self.points_radio = QtWidgets.QRadioButton("Points")
        self.lines_radio = QtWidgets.QRadioButton("Lines")
        self.pline_radio = QtWidgets.QRadioButton("PLines")
        self.poly3d_radio = QtWidgets.QRadioButton("3DPOLY")
        self.points_radio.setChecked(True)
        draw_layout = QtWidgets.QHBoxLayout()
        draw_layout.addWidget(self.points_radio)
        draw_layout.addWidget(self.lines_radio)
        draw_layout.addWidget(self.pline_radio)
        draw_layout.addWidget(self.poly3d_radio)
        self.draw_group.setLayout(draw_layout)
        layout.addWidget(self.draw_group)

        # Extra options for Points
        self.extra_options_group = QtWidgets.QGroupBox("Points options:")
        self.extra_options_group.hide()

        self.numbers_checkbox = QtWidgets.QCheckBox("Add numbers to points")
        self.numbers_checkbox.stateChanged.connect(self.toggle_font_size)

        self.font_size_input = QtWidgets.QLineEdit()
        self.font_size_input.setPlaceholderText("Text size (e.g. 0.2)")
        self.font_size_input.hide()

        extra_layout = QtWidgets.QVBoxLayout()
        extra_layout.addWidget(self.numbers_checkbox)
        extra_layout.addWidget(self.font_size_input)
        self.extra_options_group.setLayout(extra_layout)
        layout.addWidget(self.extra_options_group)

        self.points_radio.toggled.connect(self.toggle_extra_options)

        # Point selection
        self.selection_group = QtWidgets.QGroupBox("Select points:")
        self.all_radio = QtWidgets.QRadioButton("All points")
        self.separate_radio = QtWidgets.QRadioButton("Separately")
        self.range_radio = QtWidgets.QRadioButton("In range")
        self.all_radio.setChecked(True)
        selection_layout = QtWidgets.QHBoxLayout()
        selection_layout.addWidget(self.all_radio)
        selection_layout.addWidget(self.separate_radio)
        selection_layout.addWidget(self.range_radio)
        self.selection_group.setLayout(selection_layout)
        layout.addWidget(self.selection_group)

        # Layer name
        self.layer_input = QtWidgets.QLineEdit()
        self.layer_input.setPlaceholderText("Enter layer name")
        layout.addWidget(self.layer_input)

        # Generate button
        self.generate_btn = QtWidgets.QPushButton("Generate Script")
        self.generate_btn.clicked.connect(self.generate_script)
        layout.addWidget(self.generate_btn)

        # Output display
        self.output_text = QtWidgets.QPlainTextEdit()
        self.output_text.setReadOnly(False)
        layout.addWidget(self.output_text)

        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open TXT File", "", "Text Files (*.txt)")
        if file_path:
            self.file_path_label.setText(file_path)

    def toggle_extra_options(self):
        if self.points_radio.isChecked():
            self.extra_options_group.show()
        else:
            self.extra_options_group.hide()
            self.font_size_input.hide()

    def toggle_font_size(self):
        if self.numbers_checkbox.isChecked():
            self.font_size_input.show()
        else:
            self.font_size_input.hide()

    def generate_script(self):
        try:
            file_path = self.file_path_label.text()
            layer_name = self.layer_input.text().strip()

            if not os.path.isfile(file_path):
                QMessageBox.critical(self, "Error", "No valid input file selected.")
                return
            if not layer_name:
                QMessageBox.critical(self, "Error", "Please enter layer name.")
                return

            gap = " " if self.space_radio.isChecked() else "\t"
            draw_option = 1 if self.points_radio.isChecked() else \
                          2 if self.lines_radio.isChecked() else \
                          3 if self.pline_radio.isChecked() else 4

            select_separately = self.separate_radio.isChecked()
            select_range = self.range_radio.isChecked()

            data = {}
            with open(file_path, "r") as file:
                i = 0
                for line in file:
                    row = line.strip().split(gap)
                    if i == 0:
                        i += 1
                        continue
                    number = int(row[0])
                    x = row[2].replace(",", ".")
                    y = row[1].replace(",", ".")
                    h = row[3].replace(",", ".") if len(row) > 3 else "0.00"
                    data[number] = [x, y, h]

            if draw_option == 1:
                if_text_points = self.numbers_checkbox.isChecked()
                font_size = self.font_size_input.text() if if_text_points else "0.2"
            else:
                if_text_points = False
                font_size = "0.2"

            if select_separately:
                select_str, ok = QtWidgets.QInputDialog.getText(self, "Select Points", "Enter points (e.g. 1,2,3):")
                if not ok:
                    return
                select_points = [int(x.strip()) for x in select_str.split(",")]
            elif select_range:
                range_str, ok = QtWidgets.QInputDialog.getText(self, "Select Range", "Enter range (e.g. 1-7):")
                if not ok:
                    return
                start, end = [int(x.strip()) for x in range_str.split("-")]
                select_points = list(range(start, end + 1))
            else:
                select_points = list(data.keys())

            output = f"-LAYER\nMAKE {layer_name}\n\n"
            if draw_option == 2:
                output += "LINE\n"
            elif draw_option == 3:
                output += "PLINE\n"
            elif draw_option == 4:
                output += "3DPOLY\n"

            for number in select_points:
                x, y, h = data[number]
                if draw_option == 1:
                    output += f"CIRCLE {x},{y},{h} 0.05\n"
                    if if_text_points:
                        output += f"-TEXT {x},{y},{h} {font_size} 0 {number}\n"
                else:
                    output += f"{x},{y},{h}\n"

            self.output_text.setPlainText(output)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    window = AutoCADScriptGenerator()
    window.show()
    app.exec()
