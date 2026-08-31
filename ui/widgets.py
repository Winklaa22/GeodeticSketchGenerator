from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt6 import QtGui
from PyQt6.QtCore import QLocale, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDoubleValidator
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon_manager
from ui.theme import ICON_MD, ICON_SM, Color, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XS


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = _ClickableRow()
        self._header.setObjectName("accordionHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self._sections: List[AccordionSection] = []

    def add_section(self, section: AccordionSection) -> None:
        section.toggled.connect(lambda s=section: self._on_toggle(s))
        self._sections.append(section)
        self._layout.addWidget(section)
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
