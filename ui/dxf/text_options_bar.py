from __future__ import annotations

from typing import Optional, Tuple

from PyQt6 import QtCore as qc, QtWidgets as qw

from ui.i18n import tr
from ui.theme import SPACE_SM, SPACE_XS
from ui.widgets import ColorSwatchButton, NumericScrubField, decimal_validator


class TextOptionsBar(qw.QFrame):

    contentChanged = qc.pyqtSignal(str, str)
    heightChanged = qc.pyqtSignal(str, float)
    rotationChanged = qc.pyqtSignal(str, float)
    colorChanged = qc.pyqtSignal(str, tuple)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("textOptionsBar")
        self.handle: Optional[str] = None
        self._orig_text = ""
        self._orig_height = 0.0
        self._orig_rotation = 0.0
        self.hide()

        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        layout.setSpacing(SPACE_XS)

        self._content = qw.QLineEdit()
        self._content.setObjectName("textOptionsContent")
        self._content.setFixedWidth(150)
        self._content.setToolTip(tr("text_options.content_tooltip"))
        self._content.editingFinished.connect(self._emit_content)
        layout.addWidget(self._content)

        self._height = qw.QLineEdit()
        self._height.setObjectName("textOptionsField")
        self._height.setFixedWidth(54)
        self._height.setToolTip(tr("text_options.height_tooltip"))
        self._height.setValidator(decimal_validator(0.001, 9999.0, 3))
        self._height.editingFinished.connect(self._emit_height)
        layout.addWidget(self._height)

        self._rotation = NumericScrubField(0.0, 360.0, decimals=2, step=1.0, suffix="°", wrap=True)
        self._rotation.setObjectName("textOptionsField")
        self._rotation.setFixedWidth(64)
        self._rotation.setToolTip(tr("text_options.rotation_tooltip"))
        self._rotation.valueEdited.connect(self._emit_rotation)
        layout.addWidget(self._rotation)

        self._color = ColorSwatchButton((255, 255, 255), tr("text_options.color_tooltip"))
        self._color.colorChanged.connect(self._emit_color)
        layout.addWidget(self._color)

    def bind(self, handle: str, text: str, height: float, rotation: float, rgb: Tuple[int, int, int]) -> None:
        self.handle = handle
        self._orig_text, self._orig_height, self._orig_rotation = text, height, rotation
        self._content.setText(text)
        self._height.setText(f"{height:g}")
        self._rotation.set_value(rotation)
        self._color.set_color(rgb)
        self.show()
        self.adjustSize()

    def _emit_content(self) -> None:
        text = self._content.text()
        if self.handle and text and text != self._orig_text:
            self.contentChanged.emit(self.handle, text)

    def _emit_height(self) -> None:
        text = self._height.text()
        if not self.handle or not text:
            return
        height = float(text.replace(",", "."))
        if height > 0 and height != self._orig_height:
            self.heightChanged.emit(self.handle, height)

    def _emit_rotation(self, rotation: float) -> None:
        if self.handle and rotation != self._orig_rotation:
            self.rotationChanged.emit(self.handle, rotation)

    def _emit_color(self, rgb: Tuple[int, int, int]) -> None:
        if self.handle:
            self.colorChanged.emit(self.handle, rgb)
