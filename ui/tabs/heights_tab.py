"""Heights-marks drawing-mode options tab."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import QFormLayout, QLineEdit, QWidget

from core.config import HeightsOptions

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_FREQUENCY = "5"


class HeightsTab(QWidget):
    """Options for the 'Heights marks' drawing mode."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.font_size_input = QLineEdit(DEFAULT_FONT_SIZE)
        self.font_size_input.setValidator(QDoubleValidator(0.0, 9999.0, 3))
        layout.addRow("Text size", self.font_size_input)

        self.frequency_input = QLineEdit(DEFAULT_FREQUENCY)
        self.frequency_input.setValidator(QIntValidator(1, 10**6))
        layout.addRow("Frequency (every Nth point)", self.frequency_input)

    def get_options(self) -> HeightsOptions:
        """Reads the current widget state into a HeightsOptions value object."""
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        frequency = int(self.frequency_input.text() or DEFAULT_FREQUENCY)
        return HeightsOptions(font_size=font_size, frequency=frequency)
