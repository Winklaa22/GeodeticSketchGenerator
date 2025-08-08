import math
import os
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import QFileDialog, QMessageBox

class AutoCADScriptGenerator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("AutoCAD Script Generator PRO")
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
        self.heights_radio = QtWidgets.QRadioButton("Heights Marks")
        self.cable_marks_ratio = QtWidgets.QRadioButton("Cable Marks")
        self.points_radio.setChecked(False)
        draw_layout = QtWidgets.QHBoxLayout()
        draw_layout.addWidget(self.points_radio)
        draw_layout.addWidget(self.lines_radio)
        draw_layout.addWidget(self.pline_radio)
        draw_layout.addWidget(self.poly3d_radio)
        draw_layout.addWidget(self.heights_radio)
        draw_layout.addWidget(self.cable_marks_ratio)
        self.draw_group.setLayout(draw_layout)
        layout.addWidget(self.draw_group)

        # Extra options for Points
        self.extra_point_options_group = QtWidgets.QGroupBox("Points options:")
        self.extra_point_options_group.hide()

        self.numbers_checkbox = QtWidgets.QCheckBox("Add numbers to points")
        self.numbers_checkbox.stateChanged.connect(self.toggle_font_size)

        self.points_font_size_input = QtWidgets.QLineEdit()
        self.points_font_size_input.setPlaceholderText("Text size (e.g. 0.2)")
        self.points_font_size_input.setText("0.6")
        self.points_font_size_input.hide()

        self.diameter_input = QtWidgets.QLineEdit()
        self.diameter_input.setPlaceholderText("Enter diameter (e.g. 0.1)")
        self.diameter_input.setText("0.05")

        extra_points_layout = QtWidgets.QVBoxLayout()
        extra_points_layout.addWidget(self.numbers_checkbox)
        extra_points_layout.addWidget(self.points_font_size_input)
        extra_points_layout.addWidget(QtWidgets.QLabel("Circle diameter:"))
        extra_points_layout.addWidget(self.diameter_input)
        self.extra_point_options_group.setLayout(extra_points_layout)
        layout.addWidget(self.extra_point_options_group)

        # Extra options for Heights
        self.extra_heights_options_group = QtWidgets.QGroupBox("Heights Marks options:")
        self.extra_heights_options_group.hide()

        self.heights_font_size_input = QtWidgets.QLineEdit()
        self.heights_font_size_input.setPlaceholderText("Text size (e.g. 0.2)")
        self.heights_font_size_input.setText("0.6")
        self.heights_font_size_input.hide()

        self.heights_frequency_input = QtWidgets.QLineEdit()
        self.heights_frequency_input.setPlaceholderText("Heights marks frequency:")
        self.heights_frequency_input.setText("5")
        self.heights_frequency_input.hide()

        extra_heights_layout = QtWidgets.QVBoxLayout()
        extra_heights_layout.addWidget(self.heights_font_size_input)
        extra_heights_layout.addWidget(self.heights_frequency_input)
        self.extra_heights_options_group.setLayout(extra_heights_layout)
        layout.addWidget(self.extra_heights_options_group)

        # Extra options for cable marks
        self.extra_cable_marks_options_group = QtWidgets.QGroupBox("Cable marks options:")
        self.extra_cable_marks_options_group.hide()

        self.cable_marks_font_size_input = QtWidgets.QLineEdit()
        self.cable_marks_font_size_input.setPlaceholderText("Text size (e.g. 0.2)")
        self.cable_marks_font_size_input.setText("0.6")
        self.cable_marks_font_size_input.hide()

        self.cable_marks_font_text_input = QtWidgets.QLineEdit()
        self.cable_marks_font_text_input.setPlaceholderText("Put cable marks text here:")
        self.cable_marks_font_text_input.setText("eN")
        self.cable_marks_font_text_input.hide()

        self.cable_marks_frequency_input = QtWidgets.QLineEdit()
        self.cable_marks_frequency_input.setPlaceholderText("Cable marks frequency:")
        self.cable_marks_frequency_input.setText("5")
        self.cable_marks_frequency_input.hide()

        cable_marks_layout = QtWidgets.QVBoxLayout()
        cable_marks_layout.addWidget(self.cable_marks_font_size_input)
        cable_marks_layout.addWidget(self.cable_marks_frequency_input)
        cable_marks_layout.addWidget(self.cable_marks_font_text_input)
        self.extra_cable_marks_options_group.setLayout(cable_marks_layout)
        layout.addWidget(self.extra_cable_marks_options_group)


        self.cable_marks_ratio.toggled.connect(self.toggle_extra_options)
        self.points_radio.toggled.connect(self.toggle_extra_options)
        self.heights_radio.toggled.connect(self.toggle_extra_options)

        # Drawing option
        self.draw_group = QtWidgets.QGroupBox("Select if is cabinet:")
        self.cabinet_radio = QtWidgets.QRadioButton("Cabinet")
        self.cabinet_radio.setChecked(False)
        draw_layout = QtWidgets.QHBoxLayout()
        draw_layout.addWidget(self.cabinet_radio)

        self.draw_group.setLayout(draw_layout)
        layout.addWidget(self.draw_group)

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
        self.layer_group = QtWidgets.QGroupBox("Type layer name:")
        self.layer_input = QtWidgets.QLineEdit()
        self.layer_input.setPlaceholderText("Enter layer name")
        self.layer_input.setText("0")
        layer_name_layout = QtWidgets.QHBoxLayout()
        layer_name_layout.addWidget(self.layer_input)
        self.layer_group.setLayout(layer_name_layout)
        layout.addWidget(self.layer_group)

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
            self.extra_point_options_group.show()
            self.extra_heights_options_group.hide()
            self.heights_font_size_input.hide()
            self.heights_frequency_input.hide()

            self.extra_cable_marks_options_group.hide()
            self.cable_marks_font_text_input.hide()
            self.cable_marks_frequency_input.hide()
            self.cable_marks_font_size_input.hide()
        elif self.heights_radio.isChecked():
            self.extra_heights_options_group.show()
            self.extra_point_options_group.hide()
            self.points_font_size_input.hide()
            self.heights_font_size_input.show()
            self.heights_frequency_input.show()
            self.extra_cable_marks_options_group.hide()
            self.cable_marks_font_text_input.hide()
            self.cable_marks_frequency_input.hide()
            self.cable_marks_font_size_input.hide()

        elif self.cable_marks_ratio.isChecked():
            self.extra_cable_marks_options_group.show()
            self.cable_marks_font_text_input.show()
            self.cable_marks_frequency_input.show()
            self.cable_marks_font_size_input.show()
            self.extra_point_options_group.hide()
            self.extra_heights_options_group.hide()
            self.heights_font_size_input.hide()
            self.heights_frequency_input.hide()
        else:
            self.extra_point_options_group.hide()
            self.extra_heights_options_group.hide()
            self.heights_frequency_input.hide()
            self.points_font_size_input.hide()
            self.heights_font_size_input.hide()
            self.extra_cable_marks_options_group.hide()
            self.cable_marks_font_text_input.hide()
            self.cable_marks_frequency_input.hide()
            self.cable_marks_font_size_input.hide()

    def toggle_font_size(self):
        if self.numbers_checkbox.isChecked():
            self.points_font_size_input.show()
        else:
            self.points_font_size_input.hide()

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
                          3 if self.pline_radio.isChecked() else \
                          4 if self.poly3d_radio.isChecked() else \
                          5 if self.heights_radio.isChecked() else 6

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
                font_size = float(self.points_font_size_input.text()) if if_text_points else 0.2
                diameter_str = self.diameter_input.text().replace(",", ".")
                if not diameter_str:
                    diameter_str = "0.1"
                diameter = float(diameter_str)
                radius = diameter / 2
            elif draw_option == 5:
                font_size = float(self.heights_font_size_input.text())
                frequency = int(self.heights_frequency_input.text())
            elif draw_option == 6:
                font_size = float(self.cable_marks_font_size_input.text())
                frequency = int(self.cable_marks_frequency_input.text())
                cable_marks_text = self.cable_marks_font_text_input.text()
            else:
                if_text_points = False
                font_size = 0.2
                cable_marks_text = "eN"
                radius = 0
                frequency = 1

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

            # Generating output
            output = f"-LAYER\nMAKE {layer_name}\n\n"
            if draw_option == 2:
                output += "LINE\n"
            elif draw_option == 3:
                output += "PLINE\n"
            elif draw_option == 4:
                output += "3DPOLY\n"

            angle_deg = 0
            for number in select_points:
                x, y, h = data[number]
                rot = 0
                if number < select_points[-1::][0]:
                    x2, y2, h2 = data[number + 1]
                    numX, numX2 = float(x), float(x2)
                    numY, numY2 = float(y), float(y2)
                    dx = numX2 - numX
                    dy = numY2 - numY

                    angle_rad = math.atan2(dy, dx)
                    angle_deg = math.degrees(angle_rad)

                    if angle_deg < 0:
                        angle_deg += 360

                    if 90 < angle_deg < 270:
                        angle_deg += 180
                        if angle_deg >= 360:
                            angle_deg -= 360

                rot = round(angle_deg, 1)

                if draw_option == 1:
                    output += f"CIRCLE {x},{y},{h} {radius}\n"
                    if if_text_points:
                        parameterSpace = font_size / 2
                        xNum, yNum = float(x), float(y)
                        ySpace = 0
                        xSpace = 0
                        if 45 <= angle_deg < 135:
                            ySpace -= parameterSpace
                            xSpace += parameterSpace
                        elif 135 <= angle_deg < 225:
                            ySpace += parameterSpace
                            xSpace -= parameterSpace
                        elif 225 <= angle_deg < 315:
                            ySpace -= parameterSpace
                            xSpace -= parameterSpace
                        else:
                            ySpace += parameterSpace
                            xSpace -= parameterSpace

                        size = font_size
                        if self.cabinet_radio.isChecked() and number in select_points[-6::]:
                            size = font_size / 2
                            xSpace = 0
                            ySpace = 0


                        output += f"-TEXT {xNum + xSpace},{yNum + ySpace},{h} {size} 0 {number}\n"
                elif draw_option == 3:
                    output += f"{x},{y}\n"
                elif draw_option == 5:
                    xSpace = 0
                    ySpace = 0
                    if 45 <= angle_deg < 135:
                        ySpace += 0.5
                        xSpace += (float(font_size)/2)
                    elif 135 <= angle_deg < 225:
                        xSpace -= 0.5
                        ySpace += (float(font_size) / 2)
                    elif 225 <= angle_deg < 315:
                        ySpace -= 0.5
                        xSpace -= (float(font_size) / 2)
                    else:
                        xSpace += 0.5
                        ySpace -= (float(font_size) / 2)

                    if 0 <= angle_deg < 20:
                        rot = 0

                    if number % frequency == 0:
                        roundedHeight = (math.ceil(float(h) * 10) / 10)
                        output += f"-TEXT {float(x) + xSpace},{float(y) + ySpace},{h} {font_size} {rot} {roundedHeight}\n"
                elif draw_option == 6:
                    if number < select_points[-1::][0]:
                        x2, y2, h2 = data[number + 1]
                        numX, numX2 = float(x), float(x2)
                        numY, numY2 = float(y), float(y2)
                        x_mid = (numX + numX2) / 2
                        y_mid = (numY + numY2) / 2

                        xSpace = 0
                        ySpace = 0
                        if 45 <= angle_deg < 135:
                            xSpace += (float(font_size) / 2)
                        elif 135 <= angle_deg < 225:
                            ySpace += (float(font_size) / 2)
                        elif 225 <= angle_deg < 315:
                            xSpace -= (float(font_size) / 2)
                        else:
                            ySpace -= (float(font_size) / 2)

                        if 0 <= angle_deg < 20:
                            rot = 0

                        if number % frequency == 0:
                            output += f"-TEXT {x_mid + xSpace},{y_mid + ySpace},{h} {font_size} {rot} {cable_marks_text}\n"
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
