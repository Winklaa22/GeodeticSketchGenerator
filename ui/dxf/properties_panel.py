from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.dxf_document import DXFDocument
from core.entity_properties import (
    ACI_BYBLOCK,
    ACI_BYLAYER,
    BYBLOCK_COLOR,
    BYLAYER_COLOR,
    GROUP_GENERAL,
    GROUP_GEOMETRY,
    GROUP_TEXT,
    KIND_ANGLE,
    KIND_BOOL,
    KIND_COLOR,
    KIND_LAYER,
    KIND_LINETYPE,
    KIND_LINEWEIGHT,
    KIND_NUMBER,
    KIND_TEXT,
    KIND_TRANSPARENCY,
    LINEWEIGHT_BYBLOCK,
    LINEWEIGHT_BYLAYER,
    LINEWEIGHT_DEFAULT,
    LINEWEIGHTS,
    TRANSPARENCY_BYBLOCK,
    TRANSPARENCY_BYLAYER,
    TRANSPARENCY_MAX_PERCENT,
    VARIES,
    ColorValue,
    PropertyRow,
    aci_rgb,
    describe,
    selection_types,
    true_color,
)
from ui.i18n import tr
from ui.theme import SPACE_MD, SPACE_SM, SPACE_XS
from ui.widgets import Dropdown, decimal_validator, styled_line_edit

_ALL_TYPES = ""
_VARIES_KEY = "__varies__"
_PICK_COLOR_KEY = "__pick__"
_GROUP_ORDER = (GROUP_GENERAL, GROUP_GEOMETRY, GROUP_TEXT)
_NUMBER_LIMIT = 1e12
_NUMBER_DECIMALS = 4
_SWATCH_SIZE = 12
_TRANSPARENCY_STEP = 10
_BASIC_ACI = (1, 2, 3, 4, 5, 6, 7)


def _translated(key: str, fallback: str) -> str:
    text = tr(key)
    return fallback if text == key else text


def type_label(dxftype: str) -> str:
    return _translated(f"properties.type.{dxftype}", dxftype.title())


def _format_number(value: float) -> str:
    return f"{value:.{_NUMBER_DECIMALS}f}"


def _format_angle(value: float) -> str:
    text = f"{value:.{_NUMBER_DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _swatch(rgb: Tuple[int, int, int]) -> qg.QIcon:
    pixmap = qg.QPixmap(_SWATCH_SIZE, _SWATCH_SIZE)
    pixmap.fill(qg.QColor(*rgb))
    return qg.QIcon(pixmap)


def _color_label(value: ColorValue) -> str:
    if value.rgb is not None:
        return ",".join(str(channel) for channel in value.rgb)
    if value.aci == ACI_BYLAYER:
        return tr("properties.bylayer")
    if value.aci == ACI_BYBLOCK:
        return tr("properties.byblock")
    return _translated(f"properties.color.{abs(value.aci)}", tr("properties.color_index", index=abs(value.aci)))


def _lineweight_label(value: int) -> str:
    if value == LINEWEIGHT_BYLAYER:
        return tr("properties.bylayer")
    if value == LINEWEIGHT_BYBLOCK:
        return tr("properties.byblock")
    if value == LINEWEIGHT_DEFAULT:
        return tr("properties.default")
    return f"{value / 100:.2f} mm"


def _linetype_label(name: str) -> str:
    if name == "ByLayer":
        return tr("properties.bylayer")
    if name == "ByBlock":
        return tr("properties.byblock")
    return name


def _transparency_label(value: int) -> str:
    if value == TRANSPARENCY_BYLAYER:
        return tr("properties.bylayer")
    if value == TRANSPARENCY_BYBLOCK:
        return tr("properties.byblock")
    return str(value)


class _ChoiceEditor(Dropdown):

    def __init__(
        self,
        options: Sequence[Tuple[Any, str]],
        current: Any,
        commit: Callable[[Any], None],
        icons: Optional[Dict[int, qg.QIcon]] = None,
    ) -> None:
        super().__init__()
        self._values: List[Any] = []
        items: List[Tuple[str, str]] = []
        if current is VARIES:
            items.append((_VARIES_KEY, tr("properties.varies")))
            self._values.append(VARIES)
        for value, label in options:
            items.append((str(len(self._values)), label))
            self._values.append(value)
        self.set_items(items)
        for index, icon in (icons or {}).items():
            self.setItemIcon(index + (1 if current is VARIES else 0), icon)
        self._current = current
        self.setCurrentIndex(self._index_of(current))
        self._commit = commit
        self.activated.connect(self._on_activated)

    def _index_of(self, value: Any) -> int:
        for index, candidate in enumerate(self._values):
            if candidate is value or (candidate is not VARIES and candidate == value):
                return index
        return 0

    def _on_activated(self, index: int) -> None:
        value = self._values[index]
        if value is VARIES or value == self._current:
            return
        self._commit(value)

    def reset(self) -> None:
        self.setCurrentIndex(self._index_of(self._current))


class _LineEditor(qw.QLineEdit):

    def __init__(self, text: str, varies: bool, numeric: bool, commit: Callable[[str], None]) -> None:
        super().__init__(text)
        self.setObjectName("input")
        if varies:
            self.setPlaceholderText(tr("properties.varies"))
        if numeric:
            self.setValidator(decimal_validator(-_NUMBER_LIMIT, _NUMBER_LIMIT, 8))
        self._committed = text
        self._commit = commit
        self.editingFinished.connect(self._on_editing_finished)

    def _on_editing_finished(self) -> None:
        text = self.text()
        if text == self._committed or not text.strip():
            self.setText(self._committed)
            return
        self._committed = text
        self._commit(text)


class PropertiesPanel(qw.QWidget):

    propertyEdited = qc.pyqtSignal(list, str, object)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._doc: Optional[DXFDocument] = None
        self._handles: List[str] = []
        self._type_filter = _ALL_TYPES
        self._stale = False

        self._refresh_timer = qc.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh)

        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        self._filter = Dropdown()
        self._filter.activated.connect(self._on_filter_changed)
        layout.addWidget(self._filter)

        self._title = qw.QLabel()
        self._title.setObjectName("propertiesTitle")
        layout.addWidget(self._title)

        self._empty = qw.QLabel(tr("properties.nothing_selected"))
        self._empty.setObjectName("blockPanelEmpty")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._body = qw.QWidget()
        self._body_layout = qw.QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(SPACE_MD)
        layout.addWidget(self._body)
        layout.addStretch(1)

        self._refresh()

    def bind(self, doc: Optional[DXFDocument], handles: Sequence[str]) -> None:
        if doc is not self._doc or set(handles) != set(self._handles):
            self._type_filter = _ALL_TYPES
        self._doc = doc
        self._handles = list(handles)
        if self.isVisible():
            self._refresh_timer.start()
        else:
            self._stale = True

    def showEvent(self, event: qg.QShowEvent) -> None:
        super().showEvent(event)
        if self._stale:
            self._refresh_timer.start()

    def _on_filter_changed(self, _index: int) -> None:
        self._type_filter = self._filter.current_key()
        self._refresh()

    def _filtered_handles(self) -> List[str]:
        if self._doc is None:
            return []
        if self._type_filter == _ALL_TYPES:
            return [entity.dxf.handle for entity in self._doc.entities_for(self._handles)]
        return [
            entity.dxf.handle
            for entity in self._doc.entities_for(self._handles)
            if entity.dxftype() == self._type_filter
        ]

    def _refresh(self) -> None:
        self._stale = False
        self._clear_body()
        entities = self._doc.entities_for(self._handles) if self._doc is not None else []
        types = selection_types(entities)
        if self._type_filter not in {dxftype for dxftype, _count in types}:
            self._type_filter = _ALL_TYPES

        self._filter.set_items(
            [(_ALL_TYPES, tr("properties.all", count=len(entities)))]
            + [(dxftype, f"{type_label(dxftype)} ({count})") for dxftype, count in types]
        )
        self._filter.set_current_key(self._type_filter)
        self._filter.setVisible(len(types) > 1)

        if not entities:
            self._title.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._title.setVisible(len(types) == 1)
        self._title.setText(type_label(types[0][0]))
        if self._type_filter != _ALL_TYPES:
            entities = [entity for entity in entities if entity.dxftype() == self._type_filter]

        rows = describe(entities)
        metrics = qg.QFontMetrics(self.font())
        label_width = max(metrics.horizontalAdvance(self._row_label(row)) for row in rows) + SPACE_MD
        for group in _GROUP_ORDER:
            group_rows = [row for row in rows if row.group == group]
            if group_rows:
                self._body_layout.addWidget(self._build_group(group, group_rows, label_width))

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    @staticmethod
    def _row_label(row: PropertyRow) -> str:
        return _translated(f"properties.key.{row.key}", row.key)

    def _build_group(self, group: str, rows: Sequence[PropertyRow], label_width: int) -> qw.QWidget:
        box = qw.QWidget()
        layout = qw.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)
        title = qw.QLabel(tr(f"properties.group.{group}"))
        title.setObjectName("layerPanelTitle")
        layout.addWidget(title)

        grid_host = qw.QFrame()
        grid_host.setObjectName("propertiesGrid")
        grid = qw.QGridLayout(grid_host)
        grid.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        grid.setHorizontalSpacing(SPACE_MD)
        grid.setVerticalSpacing(SPACE_XS)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, label_width)
        for index, row in enumerate(rows):
            label = qw.QLabel(self._row_label(row))
            label.setObjectName("fieldLabel")
            grid.addWidget(label, index, 0)
            grid.addWidget(self._editor_for(row), index, 1)
        layout.addWidget(grid_host)
        return box

    def _emit(self, key: str, value: Any) -> None:
        handles = self._filtered_handles()
        if handles:
            self.propertyEdited.emit(handles, key, value)

    def _editor_for(self, row: PropertyRow) -> qw.QWidget:
        if not row.editable:
            return self._value_label(row)
        commit = lambda value, key=row.key: self._emit(key, value)
        if row.kind == KIND_LAYER:
            names = [info.name for info in self._doc.iter_layers()] if self._doc is not None else []
            return _ChoiceEditor([(name, name) for name in names], row.value, commit)
        if row.kind == KIND_LINETYPE:
            return _ChoiceEditor([(name, _linetype_label(name)) for name in self._linetype_names()], row.value, commit)
        if row.kind == KIND_LINEWEIGHT:
            return _ChoiceEditor([(value, _lineweight_label(value)) for value in LINEWEIGHTS], row.value, commit)
        if row.kind == KIND_TRANSPARENCY:
            return _ChoiceEditor(self._transparency_options(row.value), row.value, commit)
        if row.kind == KIND_BOOL:
            return _ChoiceEditor([(True, tr("properties.yes")), (False, tr("properties.no"))], row.value, commit)
        if row.kind == KIND_COLOR:
            return self._color_editor(row.value, commit)
        if row.kind in (KIND_NUMBER, KIND_ANGLE):
            formatter = _format_angle if row.kind == KIND_ANGLE else _format_number
            text = "" if row.value is VARIES else formatter(row.value)
            return _LineEditor(text, row.value is VARIES, True, lambda text: commit(float(text.replace(",", "."))))
        text = "" if row.value is VARIES else str(row.value)
        return _LineEditor(text, row.value is VARIES, False, commit)

    def _value_label(self, row: PropertyRow) -> qw.QLabel:
        if row.value is VARIES:
            text = tr("properties.varies")
        elif row.kind == KIND_NUMBER:
            text = _format_number(row.value)
        elif row.kind == KIND_ANGLE:
            text = _format_angle(row.value)
        else:
            text = str(row.value)
        label = qw.QLabel(text)
        label.setObjectName("propertyValue")
        label.setTextInteractionFlags(qc.Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _linetype_names(self) -> List[str]:
        names = self._doc.linetype_names() if self._doc is not None else []
        own = [name for name in names if name.lower() not in ("bylayer", "byblock")]
        return ["ByLayer", "ByBlock"] + own

    @staticmethod
    def _transparency_options(current: Any) -> List[Tuple[int, str]]:
        values = [TRANSPARENCY_BYLAYER, TRANSPARENCY_BYBLOCK]
        values += list(range(0, TRANSPARENCY_MAX_PERCENT + 1, _TRANSPARENCY_STEP))
        if current is not VARIES and current not in values:
            values.append(current)
            values[2:] = sorted(values[2:])
        return [(value, _transparency_label(value)) for value in values]

    def _color_editor(self, current: Any, commit: Callable[[Any], None]) -> qw.QWidget:
        options: List[Tuple[Any, str]] = [(BYLAYER_COLOR, tr("properties.bylayer")), (BYBLOCK_COLOR, tr("properties.byblock"))]
        options += [(ColorValue(aci), _color_label(ColorValue(aci))) for aci in _BASIC_ACI]
        if current is not VARIES and current not in [value for value, _label in options]:
            options.append((current, _color_label(current)))
        options.append((_PICK_COLOR_KEY, tr("properties.pick_color")))
        icons: Dict[int, qg.QIcon] = {}
        for index, (value, _label) in enumerate(options):
            if isinstance(value, ColorValue) and value.aci not in (ACI_BYLAYER, ACI_BYBLOCK):
                icons[index] = _swatch(value.rgb if value.rgb is not None else aci_rgb(value.aci))

        editor: Optional[_ChoiceEditor] = None

        def on_commit(value: Any) -> None:
            if value != _PICK_COLOR_KEY:
                commit(value)
                return
            picked = self._pick_color(current)
            if picked is None:
                assert editor is not None
                editor.reset()
                return
            commit(picked)

        editor = _ChoiceEditor(options, current, on_commit, icons)
        return editor

    def _pick_color(self, current: Any) -> Optional[ColorValue]:
        initial = qg.QColor(255, 255, 255)
        if isinstance(current, ColorValue) and current.aci not in (ACI_BYLAYER, ACI_BYBLOCK):
            initial = qg.QColor(*(current.rgb if current.rgb is not None else aci_rgb(current.aci)))
        dialog = qw.QColorDialog(initial, self)
        dialog.setWindowTitle(tr("widgets.choose_color_title"))
        dialog.setStyleSheet("")
        if dialog.exec() != qw.QColorDialog.DialogCode.Accepted:
            return None
        color = dialog.selectedColor()
        if not color.isValid():
            return None
        return true_color((color.red(), color.green(), color.blue()))
