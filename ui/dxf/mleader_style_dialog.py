from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from PyQt6 import QtCore as qc, QtWidgets as qw

from core.fonts import FONT_CATALOG
from core.multileader import (
    ANGLE_CONSTRAINTS,
    ARROWHEADS,
    HORIZONTAL_CONNECTIONS,
    VERTICAL_CONNECTIONS,
    MultileaderStyle,
)
from ui.i18n import tr
from ui.theme import SPACE_LG, SPACE_MD, SPACE_SM
from ui.widgets import (
    CheckField,
    ColorSwatchButton,
    Dropdown,
    decimal_validator,
    field_label,
    make_button,
    styled_line_edit,
)

_LINEWEIGHTS = (-2, -1, 13, 18, 25, 35, 50, 70)
_DEFAULT_SWATCH = (255, 255, 255)


def _lineweight_label(value: int) -> str:
    if value == -2:
        return tr("mleader.by_block")
    if value == -1:
        return tr("mleader.by_layer")
    return f"{value / 100:.2f} mm"


class _ColorField(qw.QWidget):

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_SM)
        self._by_block = CheckField(tr("mleader.by_block"))
        self._swatch = ColorSwatchButton(_DEFAULT_SWATCH, tr("text_options.color_tooltip"))
        self._by_block.toggled.connect(lambda checked: self._swatch.setEnabled(not checked))
        layout.addWidget(self._by_block)
        layout.addWidget(self._swatch)
        layout.addStretch(1)

    def set_value(self, rgb: Optional[Tuple[int, int, int]]) -> None:
        self._by_block.setChecked(rgb is None)
        self._swatch.set_color(rgb or _DEFAULT_SWATCH)
        self._swatch.setEnabled(rgb is not None)

    def value(self) -> Optional[Tuple[int, int, int]]:
        return None if self._by_block.isChecked() else self._swatch.rgb


class MultileaderPropertiesForm(qw.QScrollArea):

    def __init__(
        self,
        block_names: Sequence[str],
        linetypes: Sequence[str],
        style_mode: bool,
        parent: Optional[qw.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(qw.QFrame.Shape.NoFrame)
        self._style_mode = style_mode
        self._linetypes = list(linetypes)
        body = qw.QWidget()
        self._form = qw.QFormLayout(body)
        self._form.setContentsMargins(0, 0, SPACE_SM, 0)
        self._form.setSpacing(SPACE_SM)
        self.setWidget(body)

        self._section(tr("mleader.section_leader"))
        self._line_type = self._dropdown("mleader.line_type", [(key, tr(f"mleader.line_type_{key}")) for key in ("straight", "spline")])
        self._arrowhead = self._dropdown("mleader.arrowhead", [(key, tr(f"mleader.arrow_{key}")) for key in ARROWHEADS])
        self._arrow_block = self._dropdown(
            "mleader.arrow_block", [("", tr("mleader.arrow_block_none"))] + [(name, name) for name in block_names]
        )
        self._arrow_size = self._number("mleader.arrow_size", 0.0, 9999.0)
        self._leader_color = _ColorField()
        self._form.addRow(field_label(tr("mleader.leader_color")), self._leader_color)
        self._leader_lineweight = self._dropdown(
            "mleader.leader_lineweight", [(str(value), _lineweight_label(value)) for value in _LINEWEIGHTS]
        )
        self._leader_linetype = self._dropdown("mleader.leader_linetype", [(name, name) for name in linetypes])

        self._section(tr("mleader.section_landing"))
        self._landing_enabled = self._check("mleader.landing_enabled")
        self._landing_length = self._number("mleader.landing_length", 0.0, 9999.0)
        self._gap = self._number("mleader.gap", 0.0, 9999.0)
        angles = [(str(value), tr("mleader.angle_any") if value == 0 else f"{value}°") for value in ANGLE_CONSTRAINTS]
        self._first_angle = self._dropdown("mleader.first_angle", angles) if style_mode else None
        self._second_angle = self._dropdown("mleader.second_angle", angles) if style_mode else None

        self._section(tr("mleader.section_text"))
        self._font = self._dropdown("mleader.font", [(spec.id, spec.label) for spec in FONT_CATALOG])
        self._height = self._number("mleader.height", 0.01, 9999.0)
        self._bold = self._check("mtext.bold")
        self._italic = self._check("mtext.italic")
        self._underline = self._check("mtext.underline")
        self._text_color = _ColorField()
        self._form.addRow(field_label(tr("mleader.text_color")), self._text_color)
        self._line_spacing = self._number("mleader.line_spacing", 0.25, 4.0)
        self._text_frame = self._check("mleader.text_frame")
        self._background = self._check("mleader.background")
        self._background_scale = self._number("mleader.background_scale", 1.0, 5.0)

        self._section(tr("mleader.section_attachment"))
        self._direction = self._dropdown(
            "mleader.direction", [(key, tr(f"mleader.direction_{key}")) for key in ("horizontal", "vertical")]
        )
        horizontal = [(key, tr(f"mleader.connection_{key}")) for key in HORIZONTAL_CONNECTIONS]
        vertical = [(key, tr(f"mleader.connection_{key}")) for key in VERTICAL_CONNECTIONS]
        self._left_connection = self._dropdown("mleader.left_connection", horizontal)
        self._right_connection = self._dropdown("mleader.right_connection", horizontal)
        self._top_connection = self._dropdown("mleader.top_connection", vertical)
        self._bottom_connection = self._dropdown("mleader.bottom_connection", vertical)

        self._section(tr("mleader.section_scale"))
        self._scale = self._number("mleader.scale", 0.001, 100000.0)
        self._annotative = self._check("mleader.annotative") if style_mode else None

    def _section(self, title: str) -> None:
        label = field_label(title)
        label.setObjectName("sectionTitle")
        self._form.addRow(label)

    def _dropdown(self, key: str, items: List[Tuple[str, str]]) -> Dropdown:
        dropdown = Dropdown()
        dropdown.set_items(items)
        self._form.addRow(field_label(tr(key)), dropdown)
        return dropdown

    def _number(self, key: str, bottom: float, top: float) -> qw.QLineEdit:
        edit = styled_line_edit()
        edit.setValidator(decimal_validator(bottom, top, 3))
        self._form.addRow(field_label(tr(key)), edit)
        return edit

    def _check(self, key: str) -> CheckField:
        check = CheckField(tr(key))
        self._form.addRow("", check)
        return check

    @staticmethod
    def _set_number(edit: qw.QLineEdit, value: float) -> None:
        edit.setText(f"{value:g}")

    @staticmethod
    def _read_number(edit: qw.QLineEdit, fallback: float) -> float:
        try:
            return float(edit.text().replace(",", "."))
        except ValueError:
            return fallback

    def load(self, source: Any) -> None:
        self._source = source
        self._line_type.set_current_key(source.line_type)
        self._arrowhead.set_current_key(source.arrowhead)
        self._arrow_block.set_current_key(source.arrow_block)
        self._set_number(self._arrow_size, source.arrow_size)
        self._leader_color.set_value(source.leader_color)
        self._leader_lineweight.set_current_key(str(source.leader_lineweight))
        self._leader_linetype.set_current_key(
            next((name for name in self._linetypes if name.lower() == source.leader_linetype.lower()), source.leader_linetype)
        )
        self._landing_enabled.setChecked(source.landing_enabled)
        self._set_number(self._landing_length, source.landing_length)
        self._set_number(self._gap, source.gap)
        self._font.set_current_key(source.font)
        self._set_number(self._height, source.height)
        self._bold.setChecked(source.bold)
        self._italic.setChecked(source.italic)
        self._underline.setChecked(source.underline)
        self._text_color.set_value(source.text_color)
        self._set_number(self._line_spacing, source.line_spacing)
        self._text_frame.setChecked(source.text_frame)
        self._background.setChecked(source.background)
        self._set_number(self._background_scale, source.background_scale)
        self._direction.set_current_key(source.direction)
        self._left_connection.set_current_key(source.left_connection)
        self._right_connection.set_current_key(source.right_connection)
        self._top_connection.set_current_key(source.top_connection)
        self._bottom_connection.set_current_key(source.bottom_connection)
        self._set_number(self._scale, source.scale)
        if self._style_mode:
            assert self._first_angle is not None and self._second_angle is not None and self._annotative is not None
            self._first_angle.set_current_key(str(source.first_angle))
            self._second_angle.set_current_key(str(source.second_angle))
            self._annotative.setChecked(source.annotative)

    def values(self) -> Dict[str, Any]:
        source = self._source
        values: Dict[str, Any] = {
            "line_type": self._line_type.current_key(),
            "arrowhead": self._arrowhead.current_key(),
            "arrow_block": self._arrow_block.current_key(),
            "arrow_size": self._read_number(self._arrow_size, source.arrow_size),
            "leader_color": self._leader_color.value(),
            "leader_lineweight": int(self._leader_lineweight.current_key() or source.leader_lineweight),
            "leader_linetype": self._leader_linetype.current_key() or source.leader_linetype,
            "landing_enabled": self._landing_enabled.isChecked(),
            "landing_length": self._read_number(self._landing_length, source.landing_length),
            "gap": self._read_number(self._gap, source.gap),
            "font": self._font.current_key(),
            "height": self._read_number(self._height, source.height),
            "bold": self._bold.isChecked(),
            "italic": self._italic.isChecked(),
            "underline": self._underline.isChecked(),
            "text_color": self._text_color.value(),
            "line_spacing": self._read_number(self._line_spacing, source.line_spacing),
            "text_frame": self._text_frame.isChecked(),
            "background": self._background.isChecked(),
            "background_scale": self._read_number(self._background_scale, source.background_scale),
            "direction": self._direction.current_key(),
            "left_connection": self._left_connection.current_key(),
            "right_connection": self._right_connection.current_key(),
            "top_connection": self._top_connection.current_key(),
            "bottom_connection": self._bottom_connection.current_key(),
            "scale": self._read_number(self._scale, source.scale),
        }
        if self._style_mode:
            assert self._first_angle is not None and self._second_angle is not None and self._annotative is not None
            values["first_angle"] = int(self._first_angle.current_key() or 0)
            values["second_angle"] = int(self._second_angle.current_key() or 0)
            values["annotative"] = self._annotative.isChecked()
        return values

    def changed_values(self) -> Dict[str, Any]:
        changed = {key: value for key, value in self.values().items() if getattr(self._source, key) != value}
        if str(changed.get("leader_linetype", "")).lower() == self._source.leader_linetype.lower():
            del changed["leader_linetype"]
        return changed


class MultileaderStyleDialog(qw.QDialog):

    def __init__(
        self,
        styles: Dict[str, MultileaderStyle],
        current: str,
        in_use: Set[str],
        block_names: Sequence[str],
        linetypes: Sequence[str],
        parent: Optional[qw.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("mleader_style.title"))
        self.resize(760, 620)
        self._original = dict(styles)
        self._styles = dict(styles)
        self._current = current
        self._in_use = in_use
        self._selected: Optional[str] = None

        outer = qw.QVBoxLayout(self)
        outer.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        outer.setSpacing(SPACE_MD)
        body = qw.QHBoxLayout()
        body.setSpacing(SPACE_MD)

        left = qw.QVBoxLayout()
        left.setSpacing(SPACE_SM)
        self._list = qw.QListWidget()
        self._list.currentTextChanged.connect(self._on_selected)
        left.addWidget(self._list, 1)
        self._new_button = make_button(tr("mleader_style.new"), "secondary", self._on_new)
        self._copy_button = make_button(tr("mleader_style.copy"), "secondary", self._on_copy)
        self._delete_button = make_button(tr("mleader_style.delete"), "secondary", self._on_delete)
        self._current_button = make_button(tr("mleader_style.set_current"), "secondary", self._on_set_current)
        for button in (self._new_button, self._copy_button, self._delete_button, self._current_button):
            left.addWidget(button)
        body.addLayout(left, 1)

        self._form = MultileaderPropertiesForm(block_names, linetypes, style_mode=True)
        body.addWidget(self._form, 2)
        outer.addLayout(body, 1)

        buttons = qw.QDialogButtonBox(
            qw.QDialogButtonBox.StandardButton.Ok | qw.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._refresh_list(current)

    def _label(self, name: str) -> str:
        return f"{name}  ({tr('mleader_style.current')})" if name == self._current else name

    def _refresh_list(self, select: str) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for name in sorted(self._styles, key=str.casefold):
            item = qw.QListWidgetItem(self._label(name))
            item.setData(qc.Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)
        self._list.blockSignals(False)
        for row in range(self._list.count()):
            if self._list.item(row).data(qc.Qt.ItemDataRole.UserRole) == select:
                self._list.setCurrentRow(row)
                break
        self._on_selected()

    def _store_form(self) -> None:
        if self._selected is not None and self._selected in self._styles:
            self._styles[self._selected] = replace(self._styles[self._selected], **self._form.values()).normalized()

    def _selected_name(self) -> Optional[str]:
        item = self._list.currentItem()
        return item.data(qc.Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_selected(self, _text: str = "") -> None:
        self._store_form()
        name = self._selected_name()
        self._selected = name
        if name is not None:
            self._form.load(self._styles[name])
        self._form.setEnabled(name is not None)
        self._delete_button.setEnabled(name is not None and name != "Standard" and name not in self._in_use)

    def _ask_name(self, suggestion: str) -> Optional[str]:
        name, ok = qw.QInputDialog.getText(self, tr("mleader_style.name_title"), tr("mleader_style.name_prompt"), text=suggestion)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self._styles:
            qw.QMessageBox.warning(self, tr("mleader_style.title"), tr("mleader_style.name_taken", name=name))
            return None
        return name

    def _on_new(self) -> None:
        self._store_form()
        name = self._ask_name(tr("mleader_style.new_name"))
        if name is None:
            return
        self._styles[name] = MultileaderStyle(name=name).normalized()
        self._selected = None
        self._refresh_list(name)

    def _on_copy(self) -> None:
        self._store_form()
        source = self._selected_name()
        if source is None:
            return
        name = self._ask_name(tr("mleader_style.copy_name", name=source))
        if name is None:
            return
        self._styles[name] = replace(self._styles[source], name=name).normalized()
        self._selected = None
        self._refresh_list(name)

    def _on_delete(self) -> None:
        name = self._selected_name()
        if name is None or name == "Standard" or name in self._in_use:
            return
        del self._styles[name]
        if self._current == name:
            self._current = "Standard"
        self._selected = None
        self._refresh_list(self._current)

    def _on_set_current(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self._store_form()
        self._current = name
        self._selected = None
        self._refresh_list(name)

    def _on_accept(self) -> None:
        self._store_form()
        self.accept()

    def changed_styles(self) -> List[MultileaderStyle]:
        return [style for name, style in self._styles.items() if self._original.get(name) != style]

    def deleted_styles(self) -> List[str]:
        return [name for name in self._original if name not in self._styles]

    def current_style(self) -> str:
        return self._current


class MultileaderPropertiesDialog(qw.QDialog):

    def __init__(
        self,
        source: Any,
        block_names: Sequence[str],
        linetypes: Sequence[str],
        parent: Optional[qw.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("mleader.properties_title"))
        self.resize(460, 620)
        outer = qw.QVBoxLayout(self)
        outer.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        outer.setSpacing(SPACE_MD)
        self._form = MultileaderPropertiesForm(block_names, linetypes, style_mode=False)
        self._form.load(source)
        outer.addWidget(self._form, 1)
        buttons = qw.QDialogButtonBox(
            qw.QDialogButtonBox.StandardButton.Ok | qw.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def changed_values(self) -> Dict[str, Any]:
        return self._form.changed_values()
