from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.parser import DelimiterMode
from ui.tabs.base import SectionWidget
from ui.widgets import CheckField, SectionColumn, SegmentedControl, make_field

_GAP_OPTIONS = [
    ("auto", "Auto-detect"),
    ("space", "Space"),
    ("tab", "Tab"),
]
_STATUS_LABELS = {"auto": "Auto", "space": "Space", "tab": "Tab"}
_MODE_BY_KEY = {
    "auto": DelimiterMode.AUTO,
    "space": DelimiterMode.SPACE,
    "tab": DelimiterMode.TAB,
}


class DelimiterTab(SectionWidget):

    swap_xy_toggled = pyqtSignal(bool)
    delimiter_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.gap_control = SegmentedControl(_GAP_OPTIONS)
        self.gap_control.currentChanged.connect(lambda _key: self.delimiter_changed.emit())
        layout.addWidget(make_field("Gap type", self.gap_control))

        self.swap_xy_checkbox = CheckField("Swap X ↔ Y (geodetic)")
        self.swap_xy_checkbox.setChecked(True)
        self.swap_xy_checkbox.toggled.connect(self.swap_xy_toggled.emit)
        layout.addWidget(self.swap_xy_checkbox)
        layout.addStretch(1)

    @property
    def delimiter_mode(self) -> DelimiterMode:
        return _MODE_BY_KEY.get(self.gap_control.current() or "auto", DelimiterMode.AUTO)

    @property
    def gap_key(self) -> str:
        return self.gap_control.current() or "auto"

    @property
    def swap_xy_enabled(self) -> bool:
        return self.swap_xy_checkbox.isChecked()

    @property
    def display_name(self) -> str:
        return _STATUS_LABELS.get(self.gap_key, "Auto")

    def set_state(self, gap_key: str, swap_xy: bool) -> None:
        self.gap_control.setCurrent(gap_key)
        self.swap_xy_checkbox.setChecked(swap_xy)

    def is_modified(self) -> bool:
        return self.gap_control.current() != "auto" or not self.swap_xy_checkbox.isChecked()
