from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.config import MeasurementsOptions
from ui.widgets import LayerDropdown, SectionColumn, decimal_validator, make_field, styled_line_edit

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_OFFSET = "0.3"
DEFAULT_LAYER_NAME = "0"


class MeasurementsTab(QWidget):

    option_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.font_size_input = styled_line_edit(DEFAULT_FONT_SIZE)
        self.font_size_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.font_size_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Text size", self.font_size_input))

        self.offset_input = styled_line_edit(DEFAULT_OFFSET)
        self.offset_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.offset_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Offset from line", self.offset_input))

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

    def get_options(self) -> MeasurementsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        offset = float((self.offset_input.text() or DEFAULT_OFFSET).replace(",", "."))
        return MeasurementsOptions(font_size=font_size, offset=offset)

    def set_options(self, options: MeasurementsOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
        self.offset_input.setText(str(options.offset))

    def is_modified(self) -> bool:
        return (
            self.font_size_input.text() != DEFAULT_FONT_SIZE
            or self.offset_input.text() != DEFAULT_OFFSET
            or self.get_layer_name() not in ("", DEFAULT_LAYER_NAME)
        )
