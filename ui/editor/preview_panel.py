from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.i18n import tr
from ui.theme import Color, ICON_SM, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XL
from ui.theme.icons import icon_manager
from ui.widgets import Card, ErrorBanner, make_button


class PreviewPanel(Card):

    saveRequested = pyqtSignal()
    applyRequested = pyqtSignal()

    def __init__(self, viewer: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        layout.addLayout(self._build_header())
        self._error_banner = ErrorBanner()
        layout.addWidget(self._error_banner)
        layout.addWidget(viewer, 1)
        layout.addLayout(self._build_actions())

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(SPACE_SM)

        title = QLabel(tr("common.dxf_preview"))
        title.setObjectName("previewHeaderTitle")
        self._meta = QLabel("")
        self._meta.setObjectName("previewMeta")

        header.addWidget(title)
        header.addWidget(self._meta)
        header.addStretch(1)
        return header

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)

        self._save_button = make_button(tr("common.save_dxf"), "secondary", lambda: self.saveRequested.emit())
        self._apply_button = make_button(tr("preview.apply_to_dxf"), "primary", lambda: self.applyRequested.emit())
        self._apply_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._apply_button.setIcon(icon_manager.get("arrow_right", size=ICON_SM, color=Color.ACCENT))

        row.addWidget(self._save_button)
        row.addStretch(1)
        row.addWidget(self._apply_button)
        return row

    def set_meta(self, entity_count: int, layer_count: int) -> None:
        self._meta.setText(tr("preview.meta", entities=entity_count, layers=layer_count))

    def clear_meta(self) -> None:
        self._meta.setText("")

    def show_error(self, message: str) -> None:
        self._error_banner.show_message(message)

    def clear_error(self) -> None:
        self._error_banner.clear()

    def set_actions_enabled(self, *, save: bool, apply: bool) -> None:
        self._save_button.setEnabled(save)
        self._apply_button.setEnabled(apply)
