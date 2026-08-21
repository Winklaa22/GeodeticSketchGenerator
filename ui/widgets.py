"""Reusable "Nocturne" widgets shared across the app shell and the option tabs.

These are presentation-only building blocks (no core/ imports, no business
logic) so they can be composed freely by ui/main_window.py and ui/tabs/*.py.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt6 import QtGui
from PyQt6.QtCore import QLocale, Qt, pyqtSignal
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

from ui.theme import SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XS


def restyle(widget: QWidget) -> None:
    """Forces Qt to re-evaluate dynamic-property QSS selectors on `widget`."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


# --------------------------------------------------------------------------
# Field helpers (label-above-input groups used inside accordion sections)
# --------------------------------------------------------------------------
def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def styled_line_edit(text: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setObjectName("input")
    return edit


def decimal_validator(bottom: float, top: float, decimals: int) -> QDoubleValidator:
    """A QDoubleValidator pinned to '.' as the decimal point.

    QDoubleValidator defaults to the OS locale's separators. On machines
    where that locale uses ',' as the decimal point, a plain
    QDoubleValidator rejects '.' entirely, making it impossible to type a
    value like "0.6" into fields whose default text and parsing (float())
    both assume a dot — the field looks like it "doesn't work". Forcing the
    C locale keeps typing and parsing consistent regardless of OS locale.
    """
    validator = QDoubleValidator(bottom, top, decimals)
    validator.setLocale(QLocale(QLocale.Language.C))
    return validator


def make_field(label_text: str, field_widget: QWidget) -> QWidget:
    """A label stacked above its input/control, spaced per the Nocturne scale."""
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_XS)
    layout.addWidget(field_label(label_text))
    layout.addWidget(field_widget)
    return wrapper


class SectionColumn(QVBoxLayout):
    """A vertical stack of fields/controls with the accordion body's spacing."""

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(SPACE_LG)


# --------------------------------------------------------------------------
# Tag
# --------------------------------------------------------------------------
class Tag(QLabel):
    """Small pill label. variant in {"neutral", "accent", "success", "error"}."""

    def __init__(self, text: str = "", variant: str = "neutral", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("tag")
        self.setProperty("variant", variant)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        restyle(self)


# --------------------------------------------------------------------------
# Checkbox (a checkable flat button — renders reliably across platforms,
# unlike QCheckBox::indicator, which needs image assets to show a checkmark)
# --------------------------------------------------------------------------
class CheckField(QPushButton):
    """Drop-in for QCheckBox: same isChecked()/setChecked()/toggled API."""

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
        glyph = "☑" if checked else "☐"
        self.setText(f"{glyph}  {self._label}")


# --------------------------------------------------------------------------
# Color swatch (a solid-colored button; click opens a color picker) — used
# for both an existing DXF layer's color (ui/layer_panel.py) and a
# not-yet-created layer's planned color (ui/tabs/layer_tab.py).
# --------------------------------------------------------------------------
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
        # Without this, the dialog inherits this button's own inline
        # "background-color: rgb(...)" (it's the dialog's Qt parent),
        # painting the whole picker in whatever color was last chosen
        # instead of its normal native chrome.
        dialog.setStyleSheet("")
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color((color.red(), color.green(), color.blue()))
                self.colorChanged.emit(self._rgb)


# --------------------------------------------------------------------------
# Layer dropdown — targets one of the layers defined in ui/tabs/layer_tab.py,
# used by Points/Heights/Cable Marks/Pipe to each pick their own.
# --------------------------------------------------------------------------
class LayerDropdown(QComboBox):
    layerChanged = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("layerDropdown")
        self.currentTextChanged.connect(lambda _text: self.layerChanged.emit())

    def set_available_layers(self, names: Sequence[str], default_name: str) -> None:
        """Repopulates the list, keeping the current pick if it still
        exists, otherwise falling back to `default_name`."""
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


# --------------------------------------------------------------------------
# Segmented control
# --------------------------------------------------------------------------
class SegmentedControl(QWidget):
    """A row of mutually-exclusive pill buttons sharing one outlined track."""

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
        """Unchecks every pill, leaving no option selected."""
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


# --------------------------------------------------------------------------
# Radio-card group (bordered cards, used for Drawing Mode)
# --------------------------------------------------------------------------
class RadioCardGroup(QWidget):
    """A grid of bordered, checkable cards: either one exclusive choice
    (radio bullets, the default) or an independent multi-choice (checkbox
    bullets, `multi_select=True`) — used for Drawing Mode, where several
    modes can now be applied together in one Apply."""

    currentChanged = pyqtSignal(str)  # single-select only: the new current key
    selectionChanged = pyqtSignal(list)  # multi-select only: all checked keys

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
            bullet = "☑" if checked else "☐"
        else:
            bullet = "●" if checked else "○"
        button.setText(f"{bullet}  {label}")

    # -- single-select API --------------------------------------------------
    def setCurrent(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def current(self) -> Optional[str]:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None

    # -- multi-select API -----------------------------------------------
    def current_keys(self) -> List[str]:
        return [key for key, btn in self._buttons.items() if btn.isChecked()]

    def set_current_keys(self, keys: Iterable[str]) -> None:
        checked = set(keys)
        for key, btn in self._buttons.items():
            btn.setChecked(key in checked)


# --------------------------------------------------------------------------
# Card
# --------------------------------------------------------------------------
class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


# --------------------------------------------------------------------------
# Accordion
# --------------------------------------------------------------------------
class _ClickableRow(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AccordionSection(QWidget):
    """One collapsible group row: icon, title, modified-dot, chevron, body."""

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

        icon_label = QLabel(icon)
        icon_label.setObjectName("accordionIcon")
        title_label = QLabel(title)
        title_label.setObjectName("accordionTitle")
        self._dot = QLabel("●")
        self._dot.setObjectName("accordionDot")
        self._dot.setVisible(False)
        self._chevron = QLabel("▾")
        self._chevron.setObjectName("accordionChevron")

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
        self._chevron.setText("▴" if expanded else "▾")
        self._header.setProperty("expanded", "true" if expanded else "false")
        restyle(self._header)

    def set_modified(self, modified: bool) -> None:
        self._dot.setVisible(modified)


class Accordion(QWidget):
    """Vertical list of AccordionSections; exactly one stays expanded."""

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


# --------------------------------------------------------------------------
# File loading
# --------------------------------------------------------------------------
class DropZone(QWidget):
    """Empty-state: dashed drop target with a fallback "browse" button."""

    fileRequested = pyqtSignal()
    filesDropped = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_SM)

        icon = QLabel("\U0001F4C4")
        icon.setObjectName("dropZoneIcon")
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

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)


class DxfSourceRow(QWidget):
    """Compact secondary loader for an optional reference .DXF drawing —
    sits right below the main .TXT source, and drives the DXF preview tab."""

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

        icon = QLabel("⬡")
        icon.setObjectName("dxfSourceIcon")
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

        self._clear_button = QPushButton("✕")
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

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)


class FileCard(QWidget):
    """Loaded-state: file name, point-count tag, size, and a Change link."""

    changeRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fileCard")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_XS)

        icon = QLabel("\U0001F4C4")
        icon.setObjectName("fileCardIcon")
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


# --------------------------------------------------------------------------
# Error banner
# --------------------------------------------------------------------------
class ErrorBanner(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_SM)

        icon = QLabel("⚠")
        icon.setObjectName("errorBannerIcon")
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
