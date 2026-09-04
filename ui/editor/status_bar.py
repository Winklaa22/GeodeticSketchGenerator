from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.session import AppState
from ui.i18n import tr
from ui.theme import SPACE_LG, SPACE_SM, SPACE_XL
from ui.widgets import restyle

_STATUS_TEXT_KEYS = {
    AppState.EMPTY: "status.empty",
    AppState.READY: "status.ready",
    AppState.APPLIED: "status.applied",
    AppState.ERROR: "status.error",
}
_PLACEHOLDER = "–"


class StatusBar(QWidget):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_XL, SPACE_SM, SPACE_XL, SPACE_SM)
        layout.setSpacing(SPACE_LG)

        self._file_label = QLabel("")
        self._layer_label = QLabel("")
        self._delimiter_label = QLabel("")
        self._state_label = QLabel("")
        for label in self._labels():
            label.setObjectName("statusText")

        layout.addWidget(self._file_label)
        layout.addWidget(self._layer_label)
        layout.addWidget(self._delimiter_label)
        layout.addStretch(1)
        layout.addWidget(self._state_label)

    def _labels(self):
        return (self._file_label, self._layer_label, self._delimiter_label, self._state_label)

    def update_state(
        self, state: AppState, *, file_text: str, layer_name: str, delimiter_name: str
    ) -> None:
        empty = state is AppState.EMPTY
        self._file_label.setText(tr("status.no_file_selected") if empty else file_text)
        self._layer_label.setText(tr("status.layer_label", value=_PLACEHOLDER if empty else layer_name))
        self._delimiter_label.setText(
            tr("status.delimiter_label", value=_PLACEHOLDER if empty else delimiter_name)
        )

        self._state_label.setText(tr(_STATUS_TEXT_KEYS[state]))
        self._state_label.setProperty("variant", "error" if state is AppState.ERROR else "normal")
        restyle(self._state_label)

    def flash(self, message: str) -> None:
        self._state_label.setText(message)
