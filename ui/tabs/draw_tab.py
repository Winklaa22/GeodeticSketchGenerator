from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QRadioButton, QVBoxLayout, QWidget

from core.draw_modes import DrawMode


class DrawTab(QWidget):
    preview_relevant_toggled = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        group = QGroupBox("Drawing option")
        row = QHBoxLayout()
        self.points_radio = QRadioButton("Points")
        self.lines_radio = QRadioButton("Lines")
        self.pline_radio = QRadioButton("PLines")
        self.poly3d_radio = QRadioButton("3DPOLY")
        self.heights_radio = QRadioButton("Heights marks")
        self.cable_radio = QRadioButton("Cable marks")
        for radio in (
            self.points_radio,
            self.lines_radio,
            self.pline_radio,
            self.poly3d_radio,
            self.heights_radio,
            self.cable_radio,
        ):
            row.addWidget(radio)
        group.setLayout(row)
        layout.addWidget(group)


        self.points_radio.toggled.connect(self.preview_relevant_toggled.emit)
        self.heights_radio.toggled.connect(self.preview_relevant_toggled.emit)
        self.cable_radio.toggled.connect(self.preview_relevant_toggled.emit)

    @property
    def draw_mode(self) -> DrawMode:
        if self.points_radio.isChecked():
            return DrawMode.POINTS
        if self.lines_radio.isChecked():
            return DrawMode.LINES
        if self.pline_radio.isChecked():
            return DrawMode.PLINES
        if self.poly3d_radio.isChecked():
            return DrawMode.POLY3D
        if self.heights_radio.isChecked():
            return DrawMode.HEIGHTS
        return DrawMode.CABLE_MARKS
