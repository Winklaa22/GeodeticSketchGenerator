"""Layer accordion section."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ui.widgets import SectionColumn, make_field, styled_line_edit

DEFAULT_LAYER_NAME = "0"
SETTINGS_KEY = "layer"


class LayerTab(QWidget):

    layer_changed = pyqtSignal()

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.layer_input = styled_line_edit(settings.value(SETTINGS_KEY, DEFAULT_LAYER_NAME))
        self.layer_input.setPlaceholderText("Enter layer name")
        self.layer_input.textChanged.connect(lambda _t: self.layer_changed.emit())
        layout.addWidget(make_field("Layer name", self.layer_input))
        layout.addStretch(1)

    def get_layer_name(self) -> str:
        return self.layer_input.text()

    def persist(self, settings: QSettings) -> None:
        settings.setValue(SETTINGS_KEY, self.layer_input.text())

    def is_modified(self) -> bool:
        return self.layer_input.text() != DEFAULT_LAYER_NAME
