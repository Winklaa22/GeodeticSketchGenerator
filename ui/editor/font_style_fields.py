from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.fonts import (
    DEFAULT_FONT_ID,
    DEFAULT_LINEWEIGHT_PRESET_ID,
    FONT_CATALOG,
    LINEWEIGHT_PRESETS,
    lineweight_preset,
    lineweight_preset_for_mm,
)
from ui.i18n import tr
from ui.widgets import CheckField, Dropdown, SectionColumn, make_field


class FontStyleFields(QWidget):

    changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        column = SectionColumn(self)
        column.setContentsMargins(0, 0, 0, 0)

        self._font_dropdown = Dropdown()
        self._font_dropdown.set_items([(spec.id, spec.label) for spec in FONT_CATALOG])
        self._font_dropdown.set_current_key(DEFAULT_FONT_ID)
        self._font_dropdown.currentIndexChanged.connect(self._on_changed)
        column.addWidget(make_field(tr("fonts_panel.font_label"), self._font_dropdown))

        self._italic_check = CheckField(tr("fonts_panel.italic_checkbox"))
        self._italic_check.toggled.connect(self._on_changed)
        column.addWidget(self._italic_check)

        self._lineweight_dropdown = Dropdown()
        self._lineweight_dropdown.set_items(
            [(preset.id, tr(f"fonts_panel.lineweight_{preset.id}")) for preset in LINEWEIGHT_PRESETS]
        )
        self._lineweight_dropdown.set_current_key(DEFAULT_LINEWEIGHT_PRESET_ID)
        self._lineweight_dropdown.currentIndexChanged.connect(self._on_changed)
        column.addWidget(make_field(tr("fonts_panel.lineweight_label"), self._lineweight_dropdown))

    def _on_changed(self, *_args: object) -> None:
        self.changed.emit()

    def get_state(self) -> Tuple[str, bool, Optional[float]]:
        font_id = self._font_dropdown.current_key() or DEFAULT_FONT_ID
        italic = self._italic_check.isChecked()
        preset_id = self._lineweight_dropdown.current_key() or DEFAULT_LINEWEIGHT_PRESET_ID
        return font_id, italic, lineweight_preset(preset_id).mm

    def set_state(self, font_id: str, italic: bool, lineweight_mm: Optional[float]) -> None:
        self._font_dropdown.set_current_key(font_id)
        self._italic_check.setChecked(italic)
        self._lineweight_dropdown.set_current_key(lineweight_preset_for_mm(lineweight_mm).id)
