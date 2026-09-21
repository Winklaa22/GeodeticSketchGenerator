from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ui.editor.font_style_fields import FontStyleFields
from ui.global_settings import new_project_font_id, new_project_font_italic, new_project_font_lineweight_mm
from ui.i18n import tr
from ui.theme import SPACE_XL
from ui.widgets import SectionColumn, make_button


class FontsPanel(QWidget):

    optionsChanged = pyqtSignal()
    applyToAllRequested = pyqtSignal()

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        column = SectionColumn(self)
        column.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)

        self._fields = FontStyleFields()
        self._fields.set_state(
            new_project_font_id(settings), new_project_font_italic(settings), new_project_font_lineweight_mm(settings)
        )
        self._fields.changed.connect(self.optionsChanged.emit)
        column.addWidget(self._fields)

        self._apply_button = make_button(
            tr("fonts_panel.apply_button"), "secondary", lambda: self.applyToAllRequested.emit()
        )
        column.addWidget(self._apply_button)

        column.addStretch(1)

    def get_state(self) -> Tuple[str, bool, Optional[float]]:
        return self._fields.get_state()

    def set_state(self, font_id: str, italic: bool, lineweight_mm: Optional[float]) -> None:
        self._fields.set_state(font_id, italic, lineweight_mm)
