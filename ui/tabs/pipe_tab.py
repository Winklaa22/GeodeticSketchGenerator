"""Pipe (RURA OSŁONOWA) drawing-mode options accordion section."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.config import PipeOptions
from ui.widgets import SectionColumn, decimal_validator, make_field, styled_line_edit

DEFAULT_WIDTH = "0.16"


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
        layout.addStretch(1)

    def get_options(self) -> PipeOptions:
        """Reads the current widget state into a PipeOptions value object."""
        width = float(self.width_input.text() or DEFAULT_WIDTH)
        return PipeOptions(width=width)

    def is_modified(self) -> bool:
        return self.width_input.text() != DEFAULT_WIDTH
