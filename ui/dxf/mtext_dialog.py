from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from ui.dxf.tools import MTextValues
from ui.i18n import tr, tr_options
from ui.theme import SPACE_LG, SPACE_MD, SPACE_SM
from ui.widgets import CheckField, Dropdown, make_field

_ALIGNMENT_KEYS = [
    ("auto", "mtext.align_auto"),
    ("left", "mtext.align_left"),
    ("center", "mtext.align_center"),
    ("right", "mtext.align_right"),
]


class MTextDialog(qw.QDialog):

    def __init__(self, values: MTextValues, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("mtext.title"))
        self.resize(420, 260)

        outer = qw.QVBoxLayout(self)
        outer.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        outer.setSpacing(SPACE_MD)

        toggles = qw.QHBoxLayout()
        toggles.setSpacing(SPACE_SM)
        self._bold = CheckField(tr("mtext.bold"))
        self._bold.setChecked(values.bold)
        self._italic = CheckField(tr("mtext.italic"))
        self._italic.setChecked(values.italic)
        self._underline = CheckField(tr("mtext.underline"))
        self._underline.setChecked(values.underline)
        for toggle in (self._bold, self._italic, self._underline):
            toggles.addWidget(toggle)
        toggles.addStretch(1)
        self._alignment = Dropdown()
        self._alignment.set_items(tr_options(_ALIGNMENT_KEYS))
        self._alignment.set_current_key(values.alignment)
        toggles.addWidget(make_field(tr("mtext.alignment"), self._alignment))
        outer.addLayout(toggles)

        self._editor = qw.QPlainTextEdit(values.text)
        self._editor.setObjectName("input")
        self._editor.setPlaceholderText(tr("mtext.placeholder"))
        outer.addWidget(self._editor, 1)

        buttons = qw.QDialogButtonBox(
            qw.QDialogButtonBox.StandardButton.Ok | qw.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        accept = qg.QShortcut(qg.QKeySequence("Ctrl+Return"), self)
        accept.activated.connect(self.accept)
        self._editor.setFocus(qc.Qt.FocusReason.OtherFocusReason)

    def values(self) -> MTextValues:
        return MTextValues(
            text=self._editor.toPlainText().rstrip("\n"),
            bold=self._bold.isChecked(),
            italic=self._italic.isChecked(),
            underline=self._underline.isChecked(),
            alignment=self._alignment.current_key() or "auto",
        )
