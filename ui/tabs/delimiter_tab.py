from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QRadioButton, QWidget

from core.parser import DelimiterMode


class DelimiterTab(QWidget):


    swap_xy_toggled = pyqtSignal(bool)
    cabinet_mode_toggled = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        gap_group = QGroupBox("Gap type")
        gap_row = QHBoxLayout()
        self.auto_radio = QRadioButton("Auto-detect")
        self.space_radio = QRadioButton("Space")
        self.tab_radio = QRadioButton("Tab")
        self.auto_radio.setChecked(True)
        gap_row.addWidget(self.auto_radio)
        gap_row.addWidget(self.space_radio)
        gap_row.addWidget(self.tab_radio)
        gap_group.setLayout(gap_row)
        layout.addRow(gap_group)

        self.swap_xy_checkbox = QCheckBox("Swap X ↔ Y (geodetic)")
        self.swap_xy_checkbox.setChecked(True)
        self.swap_xy_checkbox.toggled.connect(self.swap_xy_toggled.emit)
        layout.addRow(self.swap_xy_checkbox)

        self.cabinet_mode_checkbox = QCheckBox("Cabinet mode (shrink last 6 labels)")
        self.cabinet_mode_checkbox.setChecked(False)
        self.cabinet_mode_checkbox.toggled.connect(self.cabinet_mode_toggled.emit)
        layout.addRow(self.cabinet_mode_checkbox)

    @property
    def delimiter_mode(self) -> DelimiterMode:
        if self.space_radio.isChecked():
            return DelimiterMode.SPACE
        if self.tab_radio.isChecked():
            return DelimiterMode.TAB
        return DelimiterMode.AUTO

    @property
    def cabinet_mode_enabled(self) -> bool:
        return self.cabinet_mode_checkbox.isChecked()
