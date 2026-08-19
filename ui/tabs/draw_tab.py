"""Drawing Mode accordion section."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.draw_modes import DrawMode
from ui.widgets import RadioCardGroup, SectionColumn

_MODE_OPTIONS = [
    ("points", "Points"),
    ("lines", "Lines"),
    ("plines", "PLines"),
    ("3dpoly", "3DPOLY"),
    ("heights", "Heights marks"),
    ("cable", "Cable marks"),
    ("pipe", "Pipe"),
]
_MODE_BY_KEY = {
    "points": DrawMode.POINTS,
    "lines": DrawMode.LINES,
    "plines": DrawMode.PLINES,
    "3dpoly": DrawMode.POLY3D,
    "heights": DrawMode.HEIGHTS,
    "cable": DrawMode.CABLE_MARKS,
    "pipe": DrawMode.PIPE,
}


class DrawTab(QWidget):
    mode_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.mode_group = RadioCardGroup(_MODE_OPTIONS, columns=2)
        self.mode_group.setCurrent("plines")
        self.mode_group.currentChanged.connect(lambda _key: self.mode_changed.emit())
        layout.addWidget(self.mode_group)
        layout.addStretch(1)

    @property
    def draw_mode(self) -> DrawMode:
        return _MODE_BY_KEY.get(self.mode_group.current() or "plines", DrawMode.PLINES)

    def is_modified(self) -> bool:
        return self.mode_group.current() != "plines"
