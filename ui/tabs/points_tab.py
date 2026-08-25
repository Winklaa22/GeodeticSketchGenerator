from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.config import PointsOptions
from ui.widgets import CheckField, LayerDropdown, SectionColumn, decimal_validator, make_field, styled_line_edit

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_DIAMETER = "0.05"
EMPTY_DIAMETER_FALLBACK = "0.1"
DEFAULT_LAYER_NAME = "0"


class PointsTab(QWidget):

    numbers_toggled = pyqtSignal(bool)
    option_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.numbers_checkbox = CheckField("Add numbers to points")
        self.numbers_checkbox.toggled.connect(self.numbers_toggled.emit)
        self.numbers_checkbox.toggled.connect(lambda _c: self.option_changed.emit())
        layout.addWidget(self.numbers_checkbox)

        self.font_size_input = styled_line_edit(DEFAULT_FONT_SIZE)
        self.font_size_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.font_size_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Text size", self.font_size_input))

        self.diameter_input = styled_line_edit(DEFAULT_DIAMETER)
        self.diameter_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.diameter_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Circle diameter", self.diameter_input))

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

    def get_options(self) -> PointsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        diameter = float((self.diameter_input.text() or EMPTY_DIAMETER_FALLBACK).replace(",", "."))
        return PointsOptions(
            numbers_enabled=self.numbers_checkbox.isChecked(),
            font_size=font_size,
            diameter=diameter,
        )

    def set_options(self, options: PointsOptions) -> None:
        self.numbers_checkbox.setChecked(options.numbers_enabled)
        self.font_size_input.setText(str(options.font_size))
        self.diameter_input.setText(str(options.diameter))

    def is_modified(self) -> bool:
        return (
            self.numbers_checkbox.isChecked()
            or self.font_size_input.text() != DEFAULT_FONT_SIZE
            or self.diameter_input.text() != DEFAULT_DIAMETER
            or self.get_layer_name() not in ("", DEFAULT_LAYER_NAME)
        )
