from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QLocale, QSize, Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from ui.theme import Color, ICON_SM, SPACE_LG, SPACE_XS
from ui.theme.icons import icon_manager


def restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def styled_line_edit(text: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setObjectName("input")
    return edit


def decimal_validator(bottom: float, top: float, decimals: int) -> QDoubleValidator:
    validator = QDoubleValidator(bottom, top, decimals)
    validator.setLocale(QLocale(QLocale.Language.C))
    return validator


def pin_menu_to_screen(menu: QMenu, anchor: QWidget) -> None:
    """Keep a popup menu on the monitor its anchor widget is actually on.

    Qt otherwise resolves a popup's screen from its computed global position, and on a
    multi-monitor setup with mismatched DPI scaling that position can land a pixel or two
    into the neighbouring monitor's virtual-desktop range - which sends the whole menu
    there instead of dropping it under the button. Call this before the menu becomes
    visible (on QMenu.aboutToShow, or right before exec()/popup()).
    """
    screen = anchor.screen()
    if screen is None:
        return
    menu.winId()
    handle = menu.windowHandle()
    if handle is not None:
        handle.setScreen(screen)


def make_button(text: str, variant: str, slot=None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("btn")
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot is not None:
        button.clicked.connect(slot)
    return button


def make_field(label_text: str, field_widget: QWidget) -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_XS)
    layout.addWidget(field_label(label_text))
    layout.addWidget(field_widget)
    return wrapper


class SectionColumn(QVBoxLayout):

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(SPACE_LG)


class Tag(QLabel):

    def __init__(self, text: str = "", variant: str = "neutral", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("tag")
        self.setProperty("variant", variant)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        restyle(self)


class CheckField(QPushButton):

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._label = text
        self.setObjectName("checkField")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.toggled.connect(self._paint)
        self._paint(False)

    def _paint(self, checked: bool) -> None:
        icon_name = "checkbox_checked" if checked else "checkbox_unchecked"
        color = Color.ACCENT if checked else Color.TEXT_MUTED
        self.setIcon(icon_manager.get(icon_name, size=ICON_SM, color=color))
        self.setIconSize(QSize(ICON_SM, ICON_SM))
        self.setText(self._label)
