"""Selection accordion section — which point numbers end up in the script."""
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QWidget

from core.selection import SelectionParser
from models.point import Point
from ui.widgets import SectionColumn, SegmentedControl, make_field

_SELECTION_OPTIONS = [
    ("all", "All"),
    ("separately", "Separately…"),
    ("range", "In range…"),
]


class SelectionTab(QWidget):

    selection_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.mode_control = SegmentedControl(_SELECTION_OPTIONS)
        self.mode_control.currentChanged.connect(lambda _key: self.selection_changed.emit())
        layout.addWidget(make_field("Select points", self.mode_control))
        layout.addStretch(1)

    def get_selected_numbers(self, data: Dict[int, Point]) -> List[int]:
        mode = self.mode_control.current()
        if mode == "separately":
            text, ok = QInputDialog.getText(self, "Select Points", "Enter points (e.g. 1,2,3):")
            if not ok:
                return []
            return SelectionParser.parse_separate(text)
        if mode == "range":
            text, ok = QInputDialog.getText(self, "Select Range", "Enter range (e.g. 1-7):")
            if not ok:
                return []
            return SelectionParser.parse_range(text)
        return SelectionParser.all_points(data)

    def is_modified(self) -> bool:
        return self.mode_control.current() != "all"
