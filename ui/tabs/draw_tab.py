"""Drawing Mode accordion section."""
from __future__ import annotations

from typing import List, Optional

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
_DEFAULT_KEYS = ["plines"]


class DrawTab(QWidget):
    """Multiple modes can be checked at once — Apply to DXF then runs each
    checked mode's generation in turn, as one undoable step."""

    modes_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.mode_group = RadioCardGroup(_MODE_OPTIONS, columns=2, multi_select=True)
        self.mode_group.set_current_keys(_DEFAULT_KEYS)
        self.mode_group.selectionChanged.connect(lambda _keys: self.modes_changed.emit())
        layout.addWidget(self.mode_group)
        layout.addStretch(1)

    @property
    def draw_modes(self) -> List[DrawMode]:
        return [_MODE_BY_KEY[key] for key in self.mode_group.current_keys() if key in _MODE_BY_KEY]

    @property
    def mode_keys(self) -> List[str]:
        """The plain mode keys — for project save/load, where DrawMode
        enum values aren't JSON-friendly."""
        return self.mode_group.current_keys()

    def set_mode_keys(self, keys: List[str]) -> None:
        valid = [key for key in keys if key in _MODE_BY_KEY]
        self.mode_group.set_current_keys(valid or _DEFAULT_KEYS)

    def is_modified(self) -> bool:
        return self.mode_group.current_keys() != _DEFAULT_KEYS
