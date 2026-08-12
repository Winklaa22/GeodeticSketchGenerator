from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QFormLayout, QLineEdit, QWidget

DEFAULT_LAYER_NAME = "0"
SETTINGS_KEY = "layer"


class LayerTab(QWidget):

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.layer_input = QLineEdit(settings.value(SETTINGS_KEY, DEFAULT_LAYER_NAME))
        self.layer_input.setPlaceholderText("Enter layer name")
        layout.addRow("Layer", self.layer_input)

    def get_layer_name(self) -> str:
        return self.layer_input.text()

    def persist(self, settings: QSettings) -> None:
        settings.setValue(SETTINGS_KEY, self.layer_input.text())
