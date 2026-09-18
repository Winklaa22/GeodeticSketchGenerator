from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtCore as qc, QtWidgets as qw

from ui.i18n import tr
from ui.theme import ICON_SM, SPACE_XS, Color as UiColor
from ui.theme.icons import icon_manager

_MODES = (
    ("edit", "detail_edit"),
    ("rotate", "rotate_tool"),
    ("scale", "scale_tool"),
    ("move", "move_tool"),
    ("arrow", "multileader_tool"),
)
_BUTTON_PX = 22


class DetailOptionsBar(qw.QFrame):
    """The mode switches that float above a selected detail view frame."""

    modeChanged = qc.pyqtSignal(str, str)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("detailOptionsBar")
        self.handle: Optional[str] = None
        self._mode: Optional[str] = None
        self._buttons: Dict[str, qw.QToolButton] = {}
        self.hide()

        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(SPACE_XS, 2, SPACE_XS, 2)
        layout.setSpacing(2)

        for mode, icon_name in _MODES:
            button = self._add_button(layout, icon_name, tr(f"detail_options.{mode}_tooltip"))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, key=mode: self._on_mode_clicked(key))
            self._buttons[mode] = button

    def _add_button(self, layout: qw.QHBoxLayout, icon_name: str, tooltip: str) -> qw.QToolButton:
        button = qw.QToolButton()
        button.setObjectName("detailOptionsBtn")
        button.setIcon(icon_manager.get(icon_name, size=ICON_SM, color=UiColor.TEXT_MUTED))
        button.setIconSize(qc.QSize(ICON_SM, ICON_SM))
        # QToolButton.sizeHint() pads well beyond the icon, so the size is pinned here
        # rather than left to the style - this bar floats over the drawing.
        button.setFixedSize(qc.QSize(_BUTTON_PX, _BUTTON_PX))
        button.setToolTip(tooltip)
        button.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        layout.addWidget(button)
        return button

    def bind(self, handle: str) -> None:
        if handle != self.handle:
            self.set_mode(None)
        self.handle = handle
        self.show()
        self.adjustSize()

    def mode(self) -> Optional[str]:
        return self._mode

    def set_mode(self, mode: Optional[str]) -> None:
        self._mode = mode
        for key, icon_name in _MODES:
            active = key == mode
            button = self._buttons[key]
            button.setChecked(active)
            color = UiColor.ACCENT if active else UiColor.TEXT_MUTED
            button.setIcon(icon_manager.get(icon_name, size=ICON_SM, color=color))

    def _on_mode_clicked(self, mode: str) -> None:
        # Clicking the active switch turns it off, so the frame goes back to behaving
        # like any other selected entity.
        self.set_mode(None if mode == self._mode else mode)
        if self.handle:
            self.modeChanged.emit(self.handle, self._mode or "")
