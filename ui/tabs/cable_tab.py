from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import QFormLayout, QLineEdit, QWidget

from core.config import CableOptions

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_FREQUENCY = "5"
DEFAULT_MARKS_TEXT = "eN"


class CableTab(QWidget):
    """Options for the 'Cable marks' drawing mode."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.font_size_input = QLineEdit(DEFAULT_FONT_SIZE)
        self.font_size_input.setValidator(QDoubleValidator(0.0, 9999.0, 3))
        layout.addRow("Text size", self.font_size_input)

        self.frequency_input = QLineEdit(DEFAULT_FREQUENCY)
        self.frequency_input.setValidator(QIntValidator(1, 10**6))
        layout.addRow("Frequency (every Nth segment)", self.frequency_input)

        self.marks_text_input = QLineEdit(DEFAULT_MARKS_TEXT)
        layout.addRow("Marks text", self.marks_text_input)

    def get_options(self) -> CableOptions:
        """Reads the current widget state into a CableOptions value object."""
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        frequency = int(self.frequency_input.text() or DEFAULT_FREQUENCY)
        marks_text = self.marks_text_input.text() or DEFAULT_MARKS_TEXT
        return CableOptions(font_size=font_size, frequency=frequency, marks_text=marks_text)
