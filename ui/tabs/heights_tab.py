
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QWidget

from core.config import HeightsOptions
from ui.widgets import SectionColumn, decimal_validator, make_field, styled_line_edit

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_FREQUENCY = "5"


class HeightsTab(QWidget):
    """Options for the 'Heights marks' drawing mode."""

    option_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.font_size_input = styled_line_edit(DEFAULT_FONT_SIZE)
        self.font_size_input.setValidator(decimal_validator(0.0, 9999.0, 3))
        self.font_size_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Text size", self.font_size_input))

        self.frequency_input = styled_line_edit(DEFAULT_FREQUENCY)
        self.frequency_input.setValidator(QIntValidator(1, 10**6))
        self.frequency_input.textChanged.connect(lambda _t: self.option_changed.emit())
        layout.addWidget(make_field("Frequency (every Nth point)", self.frequency_input))
        layout.addStretch(1)

    def get_options(self) -> HeightsOptions:
        """Reads the current widget state into a HeightsOptions value object."""
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        frequency = int(self.frequency_input.text() or DEFAULT_FREQUENCY)
        return HeightsOptions(font_size=font_size, frequency=frequency)

    def set_options(self, options: HeightsOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
        self.frequency_input.setText(str(options.frequency))

    def is_modified(self) -> bool:
        return self.font_size_input.text() != DEFAULT_FONT_SIZE or self.frequency_input.text() != DEFAULT_FREQUENCY
