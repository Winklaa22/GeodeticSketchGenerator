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

        # Last-confirmed text for each prompt, kept only to pre-fill the
        # dialog next time and for project save/load - not applied silently.
        self._separate_text = ""
        self._range_text = ""

    def get_selected_numbers(self, data: Dict[int, Point]) -> List[int]:
        mode = self.mode_control.current()
        if mode == "separately":
            text, ok = QInputDialog.getText(
                self, "Select Points", "Enter points (e.g. 1,2,3):", text=self._separate_text
            )
            if not ok:
                return []
            self._separate_text = text
            return SelectionParser.parse_separate(text)
        if mode == "range":
            text, ok = QInputDialog.getText(
                self, "Select Range", "Enter range (e.g. 1-7):", text=self._range_text
            )
            if not ok:
                return []
            self._range_text = text
            return SelectionParser.parse_range(text)
        return SelectionParser.all_points(data)

    @property
    def mode_key(self) -> str:
        """The plain "all"/"separately"/"range" key — for project save/load."""
        return self.mode_control.current() or "all"

    def get_expression_state(self) -> tuple[str, str]:
        """(separate_text, range_text) - the last-confirmed text for each
        prompt, for project save/load. Neither is applied to a live
        selection on its own; see get_selected_numbers."""
        return self._separate_text, self._range_text

    def set_state(self, mode_key: str, separate_text: str, range_text: str) -> None:
        self.mode_control.setCurrent(mode_key)
        self._separate_text = separate_text
        self._range_text = range_text

    def is_modified(self) -> bool:
        return self.mode_control.current() != "all"
