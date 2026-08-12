from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QCheckBox, QFormLayout, QLineEdit, QWidget

from core.config import PointsOptions

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_DIAMETER = "0.05"
EMPTY_DIAMETER_FALLBACK = "0.1"


class PointsTab(QWidget):
    """Options for the 'Points' drawing mode: circle size and optional number labels."""

    numbers_toggled = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.numbers_checkbox = QCheckBox("Add numbers to points")
        self.numbers_checkbox.stateChanged.connect(self._on_numbers_state_changed)
        layout.addRow(self.numbers_checkbox)

        self.font_size_input = QLineEdit(DEFAULT_FONT_SIZE)
        self.font_size_input.setPlaceholderText("Text size, e.g. 0.6")
        self.font_size_input.setValidator(QDoubleValidator(0.0, 9999.0, 3))
        self.font_size_input.hide()
        layout.addRow("Text size", self.font_size_input)

        self.diameter_input = QLineEdit(DEFAULT_DIAMETER)
        self.diameter_input.setPlaceholderText("Circle diameter, e.g. 0.05")
        self.diameter_input.setValidator(QDoubleValidator(0.0, 9999.0, 3))
        layout.addRow("Circle diameter", self.diameter_input)

    def _on_numbers_state_changed(self) -> None:
        enabled = self.numbers_checkbox.isChecked()
        self.font_size_input.setVisible(enabled)
        self.numbers_toggled.emit(enabled)

    def get_options(self) -> PointsOptions:
        """Reads the current widget state into a PointsOptions value object."""
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        diameter = float((self.diameter_input.text() or EMPTY_DIAMETER_FALLBACK).replace(",", "."))
        return PointsOptions(
            numbers_enabled=self.numbers_checkbox.isChecked(),
            font_size=font_size,
            diameter=diameter,
        )
