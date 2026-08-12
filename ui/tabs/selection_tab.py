from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QInputDialog, QRadioButton, QVBoxLayout, QWidget

from core.selection import SelectionParser
from models.point import Point


class SelectionTab(QWidget):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        group = QGroupBox("Select points")
        row = QHBoxLayout()
        self.all_radio = QRadioButton("All points")
        self.separate_radio = QRadioButton("Separately…")
        self.range_radio = QRadioButton("In range…")
        self.all_radio.setChecked(True)
        row.addWidget(self.all_radio)
        row.addWidget(self.separate_radio)
        row.addWidget(self.range_radio)
        group.setLayout(row)
        layout.addWidget(group)

    def get_selected_numbers(self, data: Dict[int, Point]) -> List[int]:

        if self.separate_radio.isChecked():
            text, ok = QInputDialog.getText(self, "Select Points", "Enter points (e.g. 1,2,3):")
            if not ok:
                return []
            return SelectionParser.parse_separate(text)
        if self.range_radio.isChecked():
            text, ok = QInputDialog.getText(self, "Select Range", "Enter range (e.g. 1-7):")
            if not ok:
                return []
            return SelectionParser.parse_range(text)
        return SelectionParser.all_points(data)
