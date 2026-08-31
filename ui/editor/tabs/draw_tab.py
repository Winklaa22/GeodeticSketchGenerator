from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.draw_modes import DrawMode
from ui.editor.mode_registry import MODE_SPECS, SPEC_BY_KEY
from ui.editor.tabs.base import SectionWidget
from ui.widgets import RadioCardGroup, SectionColumn

_MODE_OPTIONS = [(spec.key, spec.mode_label) for spec in MODE_SPECS]
_DEFAULT_KEYS = ["plines"]


class DrawTab(SectionWidget):

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
        return [SPEC_BY_KEY[key].draw_mode for key in self.mode_keys if key in SPEC_BY_KEY]

    @property
    def mode_keys(self) -> List[str]:
        return self.mode_group.current_keys()

    def set_mode_keys(self, keys: List[str]) -> None:
        valid = [key for key in keys if key in SPEC_BY_KEY]
        self.mode_group.set_current_keys(valid or _DEFAULT_KEYS)

    def is_modified(self) -> bool:
        return self.mode_keys != _DEFAULT_KEYS
