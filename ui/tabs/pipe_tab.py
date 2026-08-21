"""Pipe (RURA OSŁONOWA) drawing-mode options accordion section."""
from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.config import PipeOptions
from ui.widgets import LayerDropdown, SectionColumn, decimal_validator, make_field, styled_line_edit

DEFAULT_WIDTH = "0.16"
DEFAULT_LAYER_NAME = "0"


class PipeTab(QWidget):
    """Options for the 'Pipe' drawing mode: the casing's width — the two
    parallel lines are drawn this far apart, straddling the cable route."""

    option_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.width_input = styled_line_edit(DEFAULT_WIDTH)
        self.width_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.width_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Pipe width", self.width_input))

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

    def get_options(self) -> PipeOptions:
        """Reads the current widget state into a PipeOptions value object."""
        width = float(self.width_input.text() or DEFAULT_WIDTH)
        return PipeOptions(width=width)

    def set_options(self, options: PipeOptions) -> None:
        self.width_input.setText(str(options.width))

    def is_modified(self) -> bool:
        return self.width_input.text() != DEFAULT_WIDTH or self.get_layer_name() not in ("", DEFAULT_LAYER_NAME)
