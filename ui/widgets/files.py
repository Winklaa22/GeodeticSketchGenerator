from __future__ import annotations

from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.theme import Color, ICON_MD, ICON_SM, SPACE_MD, SPACE_SM, SPACE_XS
from ui.theme.icons import icon_manager
from ui.widgets.primitives import Tag, restyle


class DropZone(QWidget):

    fileRequested = pyqtSignal()
    filesDropped = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_SM)

        icon = QLabel()
        icon.setObjectName("dropZoneIcon")
        icon.setPixmap(icon_manager.get("txt_file_icon", size=26, color=Color.TEXT_FAINT).pixmap(26, 26))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Drag & drop a .TXT file here")
        hint.setObjectName("dropZoneHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._button = QPushButton("Select input .TXT file")
        self._button.setObjectName("btn")
        self._button.setProperty("variant", "secondary")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self.fileRequested.emit)

        layout.addWidget(icon)
        layout.addWidget(hint)
        layout.addWidget(self._button, 0, Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)


class DxfSourceRow(QWidget):

    fileRequested = pyqtSignal()
    filesDropped = pyqtSignal(list)
    clearRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dxfSourceRow")
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_SM)

        icon = QLabel()
        icon.setObjectName("dxfSourceIcon")
        icon.setPixmap(icon_manager.get("dxf_icon", size=18, color=Color.TEXT_MUTED).pixmap(18, 18))
        layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        self._title = QLabel("")
        self._title.setObjectName("dxfSourceTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("dxfSourceSubtitle")
        self._subtitle.setWordWrap(True)
        text_col.addWidget(self._title)
        text_col.addWidget(self._subtitle)
        layout.addLayout(text_col, 1)

        self._button = QPushButton("")
        self._button.setObjectName("btn")
        self._button.setProperty("variant", "secondary")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self.fileRequested.emit)
        layout.addWidget(self._button)

        self._clear_button = QPushButton()
        self._clear_button.setIcon(icon_manager.get("dxf_source_clear", size=ICON_SM, color=Color.ACCENT))
        self._clear_button.setObjectName("linkButton")
        self._clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_button.clicked.connect(self.clearRequested.emit)
        layout.addWidget(self._clear_button)

        self.set_empty()

    def set_empty(self) -> None:
        self._title.setText("DXF preview")
        self._set_subtitle("Drag & drop, or browse a .dxf file", "muted")
        self._button.setText("Browse")
        self._clear_button.hide()

    def set_file(self, name: str, entity_count: int) -> None:
        self._title.setText(name)
        self._set_subtitle(f"{entity_count} entities · shown in preview", "muted")
        self._button.setText("Change")
        self._clear_button.show()

    def show_error(self, message: str) -> None:
        self._title.setText("Couldn't load DXF")
        self._set_subtitle(message, "error")

    def _set_subtitle(self, text: str, variant: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setProperty("variant", variant)
        restyle(self._subtitle)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)


class FileCard(QWidget):

    changeRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fileCard")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_XS)

        icon = QLabel()
        icon.setObjectName("fileCardIcon")
        icon.setPixmap(icon_manager.get("txt_file_icon", size=22, color=Color.TEXT).pixmap(22, 22))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._name = QLabel("")
        self._name.setObjectName("fileCardName")
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(SPACE_SM)
        self._points_tag = Tag("", variant="accent")
        self._size_label = QLabel("")
        self._size_label.setObjectName("fileCardMeta")
        meta_row.addStretch(1)
        meta_row.addWidget(self._points_tag)
        meta_row.addWidget(self._size_label)
        meta_row.addStretch(1)

        self._change_button = QPushButton("Change")
        self._change_button.setObjectName("linkButton")
        self._change_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_button.clicked.connect(self.changeRequested.emit)

        layout.addWidget(icon)
        layout.addWidget(self._name)
        meta_wrap = QWidget()
        meta_wrap.setLayout(meta_row)
        layout.addWidget(meta_wrap)
        layout.addWidget(self._change_button, 0, Qt.AlignmentFlag.AlignCenter)

    def set_file(self, name: str, points_count: int, size_text: str) -> None:
        self._name.setText(name)
        self._points_tag.setText(f"{points_count} points")
        self._size_label.setText(size_text)


class ErrorBanner(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_SM)

        icon = QLabel()
        icon.setObjectName("errorBannerIcon")
        icon.setPixmap(icon_manager.get("warning_icon", size=ICON_MD, color=Color.ERROR).pixmap(ICON_MD, ICON_MD))
        self._text = QLabel("")
        self._text.setObjectName("errorBannerText")
        self._text.setWordWrap(True)

        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)
        self.hide()

    def show_message(self, message: str) -> None:
        self._text.setText(message)
        self.show()

    def clear(self) -> None:
        self._text.clear()
        self.hide()
