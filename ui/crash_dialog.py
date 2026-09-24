from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.theme import Color, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XL
from ui.theme.icons import icon_manager
from ui.theme.style import APP_STYLESHEET
from ui.widgets import make_button

_ICON_SIZE = 28
_COPIED_LABEL_MS = 1200


class CrashDialog(QDialog):

    def __init__(self, summary: str, details: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("crash.title"))
        self.setStyleSheet(APP_STYLESHEET)
        self.setModal(True)
        self.resize(560, 420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_LG)
        outer.setSpacing(SPACE_LG)

        header = QHBoxLayout()
        header.setSpacing(SPACE_MD)
        icon = QLabel()
        icon.setPixmap(icon_manager.get("warning_icon", size=_ICON_SIZE, color=Color.ERROR).pixmap(_ICON_SIZE, _ICON_SIZE))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setSpacing(SPACE_SM)
        heading = QLabel(tr("crash.heading"))
        heading.setObjectName("startHeading")
        text_column.addWidget(heading)
        description = QLabel(tr("crash.description"))
        description.setObjectName("crashDescription")
        description.setWordWrap(True)
        text_column.addWidget(description)
        summary_label = QLabel(summary)
        summary_label.setObjectName("crashSummary")
        summary_label.setWordWrap(True)
        text_column.addWidget(summary_label)
        header.addLayout(text_column, 1)
        outer.addLayout(header)

        details_view = QPlainTextEdit(details)
        details_view.setObjectName("crashDetails")
        details_view.setReadOnly(True)
        details_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        outer.addWidget(details_view, 1)

        footer = QHBoxLayout()
        footer.setSpacing(SPACE_SM)
        self._copy_button = make_button(tr("crash.copy_details"), "secondary", lambda: self._copy(details))
        footer.addWidget(self._copy_button)
        footer.addStretch(1)
        close_button = make_button(tr("crash.close_program"), "primary", self.accept)
        footer.addWidget(close_button)
        outer.addLayout(footer)

    def _copy(self, details: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(details)
        self._copy_button.setText(tr("crash.copied"))
        QTimer.singleShot(_COPIED_LABEL_MS, lambda: self._copy_button.setText(tr("crash.copy_details")))
