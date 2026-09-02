from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.theme import Color, ICON_MD, ICON_SM, SPACE_LG, SPACE_MD, SPACE_SM
from ui.theme.icons import icon_manager
from ui.widgets.primitives import restyle


class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class _ClickableRow(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AccordionSection(QWidget):

    toggled = pyqtSignal()

    def __init__(self, icon: str, title: str, content: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._content = content
        self._expanded = False
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = _ClickableRow()
        self._header.setObjectName("accordionHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._header.clicked.connect(self.toggled.emit)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        header_layout.setSpacing(SPACE_SM)

        icon_label = QLabel()
        icon_label.setObjectName("accordionIcon")
        icon_label.setPixmap(icon_manager.get(icon, size=ICON_MD, color=Color.TEXT_MUTED).pixmap(ICON_MD, ICON_MD))
        title_label = QLabel(title)
        title_label.setObjectName("accordionTitle")
        self._dot = QLabel()
        self._dot.setObjectName("accordionDot")
        self._dot.setPixmap(icon_manager.get("modified_dot", size=ICON_SM, color=Color.ACCENT).pixmap(ICON_SM, ICON_SM))
        self._dot.setVisible(False)
        self._chevron = QLabel()
        self._chevron.setObjectName("accordionChevron")
        self._chevron.setPixmap(
            icon_manager.get("chevron_collapsed", size=ICON_SM, color=Color.TEXT_FAINT).pixmap(ICON_SM, ICON_SM)
        )

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self._dot)
        header_layout.addWidget(self._chevron)

        content.setObjectName("accordionContent")
        content.setVisible(False)

        outer.addWidget(self._header)
        outer.addWidget(content)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._content.setVisible(expanded)
        chevron_name = "chevron_expanded" if expanded else "chevron_collapsed"
        self._chevron.setPixmap(
            icon_manager.get(chevron_name, size=ICON_SM, color=Color.TEXT_FAINT).pixmap(ICON_SM, ICON_SM)
        )
        self._header.setProperty("expanded", "true" if expanded else "false")
        restyle(self._header)

    def set_modified(self, modified: bool) -> None:
        self._dot.setVisible(modified)


class Accordion(QWidget):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("accordion")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self._sections: List[AccordionSection] = []

    def add_section(self, section: AccordionSection) -> None:
        section.toggled.connect(lambda s=section: self._on_toggle(s))
        self._sections.append(section)
        self._layout.insertWidget(self._layout.count() - 1, section)
        if len(self._sections) == 1:
            section.set_expanded(True)

    def _on_toggle(self, section: AccordionSection) -> None:
        if section.is_expanded():
            return
        for s in self._sections:
            s.set_expanded(s is section)

    def expand(self, index: int) -> None:
        if 0 <= index < len(self._sections):
            self._on_toggle(self._sections[index])

