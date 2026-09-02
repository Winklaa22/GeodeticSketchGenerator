from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QWidget

from core.title_block import TitleBlockProfile
from ui.editor.title_block_store import load_profile, save_profile
from ui.theme import SPACE_LG
from ui.widgets import SectionColumn, make_field, styled_line_edit


def _plain_text_edit(text: str = "") -> QPlainTextEdit:
    edit = QPlainTextEdit(text)
    edit.setObjectName("input")
    edit.setFixedHeight(64)
    return edit


class TitleBlockProfileDialog(QDialog):

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Title Block Profile")
        self.setMinimumWidth(420)
        self._settings = settings

        column = SectionColumn(self)
        column.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        self.surveyor_title_input = styled_line_edit("")
        column.addWidget(make_field("Surveyor title", self.surveyor_title_input))

        self.surveyor_name_input = styled_line_edit("")
        column.addWidget(make_field("Surveyor name", self.surveyor_name_input))

        self.license_text_input = _plain_text_edit("")
        column.addWidget(make_field("License text", self.license_text_input))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)

        self._load_profile()

    def _load_profile(self) -> None:
        profile = load_profile(self._settings)
        self.surveyor_title_input.setText(profile.surveyor_title)
        self.surveyor_name_input.setText(profile.surveyor_name)
        self.license_text_input.setPlainText(profile.license_text)

    def _collect_profile(self) -> TitleBlockProfile:
        return TitleBlockProfile(
            surveyor_title=self.surveyor_title_input.text(),
            surveyor_name=self.surveyor_name_input.text(),
            license_text=self.license_text_input.toPlainText(),
        )

    def _on_accept(self) -> None:
        save_profile(self._settings, self._collect_profile())
        self.accept()
