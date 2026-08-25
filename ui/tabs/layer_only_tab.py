from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from ui.widgets import LayerDropdown, SectionColumn, make_field

DEFAULT_LAYER_NAME = "0"


class LayerOnlyTab(QWidget):
    option_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.layer_dropdown = LayerDropdown()
        self.layer_dropdown.layerChanged.connect(self.option_changed.emit)
        layout.addWidget(make_field("Layer", self.layer_dropdown))
        layout.addStretch(1)

    def set_available_layers(self, names: Sequence[str], default_name: str) -> None:
        self.layer_dropdown.set_available_layers(names, default_name)

    def get_layer_name(self) -> str:
        return self.layer_dropdown.layer_name()

    def set_layer_name(self, name: str) -> None:
        self.layer_dropdown.set_layer_name(name)

    def is_modified(self) -> bool:
        return self.get_layer_name() not in ("", DEFAULT_LAYER_NAME)
