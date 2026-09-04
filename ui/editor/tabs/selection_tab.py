from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QWidget

from core.selection import SelectionParser
from models.point import Point
from ui.editor.tabs.base import SectionWidget
from ui.i18n import tr, tr_options
from ui.widgets import SectionColumn, SegmentedControl, make_field

_SELECTION_OPTION_KEYS = [
    ("all", "tabs.selection_all"),
    ("separately", "tabs.selection_separately"),
    ("range", "tabs.selection_range"),
]


class SelectionTab(SectionWidget):

    selection_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.mode_control = SegmentedControl(tr_options(_SELECTION_OPTION_KEYS))
        self.mode_control.currentChanged.connect(lambda _key: self.selection_changed.emit())
        layout.addWidget(make_field(tr("tabs.select_points_field"), self.mode_control))
        layout.addStretch(1)

        self._separate_text = ""
        self._range_text = ""

    def get_selected_numbers(self, data: Dict[int, Point]) -> List[int]:
        mode = self.mode_control.current()
        if mode == "separately":
            text, ok = QInputDialog.getText(
                self, tr("tabs.select_points_title"), tr("tabs.select_points_label"), text=self._separate_text
            )
            if not ok:
                return []
            self._separate_text = text
            return SelectionParser.parse_separate(text)
        if mode == "range":
            text, ok = QInputDialog.getText(
                self, tr("tabs.select_range_title"), tr("tabs.select_range_label"), text=self._range_text
            )
            if not ok:
                return []
            self._range_text = text
            return SelectionParser.parse_range(text)
        return SelectionParser.all_points(data)

    @property
    def mode_key(self) -> str:
        return self.mode_control.current() or "all"

    def get_expression_state(self) -> tuple[str, str]:
        return self._separate_text, self._range_text

    def set_state(self, mode_key: str, separate_text: str, range_text: str) -> None:
        self.mode_control.setCurrent(mode_key)
        self._separate_text = separate_text
        self._range_text = range_text

    def is_modified(self) -> bool:
        return self.mode_control.current() != "all"
