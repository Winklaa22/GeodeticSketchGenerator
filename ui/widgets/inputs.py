from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Color, ICON_MD, ICON_SM, SPACE_SM
from ui.theme.icons import icon_manager


class ColorSwatchButton(QToolButton):

    colorChanged = pyqtSignal(tuple)

    def __init__(
        self, rgb: Tuple[int, int, int], tooltip: str = "Change color", parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("colorSwatchBtn")
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rgb = rgb
        self._apply_style()
        self.clicked.connect(self._pick_color)

    @property
    def rgb(self) -> Tuple[int, int, int]:
        return self._rgb

    def set_color(self, rgb: Tuple[int, int, int]) -> None:
        self._rgb = rgb
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"background-color: rgb{self._rgb};")

    def _pick_color(self) -> None:
        dialog = QColorDialog(QColor(*self._rgb), self)
        dialog.setWindowTitle("Choose Color")
        dialog.setStyleSheet("")
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color((color.red(), color.green(), color.blue()))
                self.colorChanged.emit(self._rgb)


class Dropdown(QComboBox):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropdown")
        self._keys: List[str] = []

    def set_items(self, items: Sequence[Tuple[str, str]]) -> None:
        current = self.current_key()
        self._keys = [key for key, _label in items]
        self.blockSignals(True)
        self.clear()
        self.addItems([label for _key, label in items])
        self.blockSignals(False)
        if current in self._keys:
            self.set_current_key(current)

    def current_key(self) -> str:
        index = self.currentIndex()
        return self._keys[index] if 0 <= index < len(self._keys) else ""

    def set_current_key(self, key: str) -> None:
        if key in self._keys:
            self.setCurrentIndex(self._keys.index(key))


class LayerDropdown(QComboBox):
    layerChanged = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("layerDropdown")
        self.currentTextChanged.connect(lambda _text: self.layerChanged.emit())

    def set_available_layers(self, names: Sequence[str], default_name: str) -> None:
        wanted = self.currentText() or default_name
        self.blockSignals(True)
        self.clear()
        self.addItems(names)
        self.setCurrentText(wanted if wanted in names else default_name)
        self.blockSignals(False)

    def layer_name(self) -> str:
        return self.currentText()

    def set_layer_name(self, name: str) -> None:
        index = self.findText(name)
        if index >= 0:
            self.setCurrentIndex(index)


class SegmentedControl(QWidget):

    currentChanged = pyqtSignal(str)

    def __init__(self, options: Sequence[Tuple[str, str]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: Dict[str, QPushButton] = {}
        for key, label in options:
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, k=key: self.currentChanged.emit(k))
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._buttons[key] = btn
        if options:
            self._buttons[options[0][0]].setChecked(True)

    def setCurrent(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def clearSelection(self) -> None:
        checked = self._group.checkedButton()
        if checked is not None:
            self._group.setExclusive(False)
            checked.setChecked(False)
            self._group.setExclusive(True)

    def current(self) -> Optional[str]:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None

    def setButtonEnabled(self, key: str, enabled: bool) -> None:
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setEnabled(enabled)


class SidebarNav(QWidget):

    currentChanged = pyqtSignal(str)

    def __init__(self, items: Sequence[Tuple[str, str, str]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarNav")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: Dict[str, QPushButton] = {}
        self._icons: Dict[str, str] = {}
        for key, label, icon_name in items:
            btn = QPushButton(label)
            btn.setObjectName("settingsNavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(ICON_MD, ICON_MD))
            btn.clicked.connect(lambda _checked, k=key: self.currentChanged.emit(k))
            btn.toggled.connect(lambda checked, k=key: self._paint(k, checked))
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._buttons[key] = btn
            self._icons[key] = icon_name
        for key in self._buttons:
            self._paint(key, False)
        if items:
            self._buttons[items[0][0]].setChecked(True)

    def _paint(self, key: str, checked: bool) -> None:
        color = Color.ACCENT if checked else Color.TEXT_MUTED
        self._buttons[key].setIcon(icon_manager.get(self._icons[key], size=ICON_MD, color=color))

    def setCurrent(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def current(self) -> Optional[str]:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None


class RadioCardGroup(QWidget):

    currentChanged = pyqtSignal(str)
    selectionChanged = pyqtSignal(list)

    def __init__(
        self,
        options: Sequence[Tuple[str, str]],
        columns: int = 2,
        parent: Optional[QWidget] = None,
        multi_select: bool = False,
    ) -> None:
        super().__init__(parent)
        self._multi_select = multi_select
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(SPACE_SM)

        self._group = QButtonGroup(self)
        self._group.setExclusive(not multi_select)
        self._buttons: Dict[str, QPushButton] = {}
        self._labels: Dict[str, str] = dict(options)
        for index, (key, label) in enumerate(options):
            btn = QPushButton()
            btn.setObjectName("radioCard")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.toggled.connect(lambda checked, b=btn, lbl=label: self._paint(b, lbl, checked))
            if multi_select:
                btn.toggled.connect(lambda _checked: self.selectionChanged.emit(self.current_keys()))
            else:
                btn.clicked.connect(lambda _checked, k=key: self.currentChanged.emit(k))
            self._paint(btn, label, False)
            self._group.addButton(btn)
            grid.addWidget(btn, index // columns, index % columns)
            self._buttons[key] = btn
        if options and not multi_select:
            self._buttons[options[0][0]].setChecked(True)
            self._paint(self._buttons[options[0][0]], options[0][1], True)

    def _paint(self, button: QPushButton, label: str, checked: bool) -> None:
        if self._multi_select:
            icon_name = "checkbox_checked" if checked else "checkbox_unchecked"
        else:
            icon_name = "radio_checked" if checked else "radio_unchecked"
        color = Color.ACCENT if checked else Color.TEXT_MUTED
        button.setIcon(icon_manager.get(icon_name, size=ICON_SM, color=color))
        button.setIconSize(QSize(ICON_SM, ICON_SM))
        button.setText(label)

    def setCurrent(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def current(self) -> Optional[str]:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None

    def current_keys(self) -> List[str]:
        return [key for key, btn in self._buttons.items() if btn.isChecked()]

    def set_current_keys(self, keys: Iterable[str]) -> None:
        checked = set(keys)
        for key, btn in self._buttons.items():
            btn.setChecked(key in checked)

