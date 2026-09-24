from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QLineEdit, QWidget

from core.project import SelectionState
from core.selection import SelectionParser
from models.point import Point
from ui.i18n import tr, tr_options
from ui.widgets import (
    CheckField,
    LayerDropdown,
    SectionColumn,
    SegmentedControl,
    decimal_validator,
    make_field,
    styled_line_edit,
)

DEFAULT_LAYER_NAME = "0"
UNSET_LAYER_NAMES = ("", DEFAULT_LAYER_NAME)

_SELECTION_OPTION_KEYS = [
    ("all", "tabs.selection_all"),
    ("separately", "tabs.selection_separately"),
    ("range", "tabs.selection_range"),
]


@dataclass(frozen=True)
class NoOptions:
    pass


class SectionWidget(QWidget):

    def is_modified(self) -> bool:
        return False


class LayeredOptionsTab(SectionWidget):

    option_changed = pyqtSignal()

    DEFAULT_OPTIONS: Any = NoOptions()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._column = SectionColumn(self)
        self._build_fields()
        self._build_selection_fields()
        self.layer_dropdown = LayerDropdown()
        self.layer_dropdown.layerChanged.connect(self.option_changed.emit)
        self._column.addWidget(make_field(tr("common.layer_field"), self.layer_dropdown))
        self._column.addStretch(1)

    def _build_selection_fields(self) -> None:
        self._selection_control = SegmentedControl(tr_options(_SELECTION_OPTION_KEYS))
        self._selection_control.currentChanged.connect(self._on_selection_mode_changed)
        self._add_field(tr("tabs.select_points_field"), self._selection_control)

        # One field serves both expression modes, each keeping its own text, so switching
        # back and forth does not make the user retype what they already had.
        self._selection_texts = {"separately": "", "range": ""}
        self._selection_edit = styled_line_edit("")
        self._selection_edit.textChanged.connect(self._on_selection_text_changed)
        self._column.addWidget(self._selection_edit)
        self._sync_selection_field()

    def _on_selection_mode_changed(self, _key: str) -> None:
        self._sync_selection_field()
        self.option_changed.emit()

    def _on_selection_text_changed(self, text: str) -> None:
        mode = self.selection_mode
        if mode in self._selection_texts:
            self._selection_texts[mode] = text
        self.option_changed.emit()

    def _sync_selection_field(self) -> None:
        mode = self.selection_mode
        expression = mode in self._selection_texts
        self._selection_edit.setVisible(expression)
        if expression:
            self._selection_edit.setPlaceholderText(
                tr("tabs.select_range_label" if mode == "range" else "tabs.select_points_label")
            )
            with QSignalBlocker(self._selection_edit):
                self._selection_edit.setText(self._selection_texts[mode])

    @property
    def selection_mode(self) -> str:
        return self._selection_control.current() or "all"

    def get_selected_numbers(self, data: Dict[int, Point]) -> List[int]:
        mode = self.selection_mode
        if mode == "separately":
            return SelectionParser.parse_separate(self._selection_texts["separately"])
        if mode == "range":
            return SelectionParser.parse_range(self._selection_texts["range"])
        return SelectionParser.all_points(data)

    def get_selection_state(self) -> SelectionState:
        return SelectionState(
            mode=self.selection_mode,
            separate_text=self._selection_texts["separately"],
            range_text=self._selection_texts["range"],
        )

    def set_selection_state(self, state: SelectionState) -> None:
        self._selection_texts["separately"] = state.separate_text
        self._selection_texts["range"] = state.range_text
        self._selection_control.setCurrent(state.mode)
        self._sync_selection_field()

    def _build_fields(self) -> None:
        pass

    def _add_widget(self, widget: QWidget) -> QWidget:
        self._column.addWidget(widget)
        return widget

    def _add_field(self, label: str, widget: QWidget) -> QWidget:
        self._column.addWidget(make_field(label, widget))
        return widget

    def _add_check_field(self, label: str, checked: bool = False) -> CheckField:
        checkbox = CheckField(label)
        checkbox.setChecked(checked)
        checkbox.toggled.connect(lambda _checked: self.option_changed.emit())
        self._add_widget(checkbox)
        return checkbox

    def _add_decimal_field(
        self, label: str, default: str, maximum: float = 9999.0, decimals: int = 3
    ) -> QLineEdit:
        edit = styled_line_edit(default)
        edit.setValidator(decimal_validator(0.0, maximum, decimals))
        edit.textChanged.connect(lambda _text: self.option_changed.emit())
        self._add_field(label, edit)
        return edit

    def _add_int_field(self, label: str, default: str, minimum: int = 1, maximum: int = 10**6) -> QLineEdit:
        edit = styled_line_edit(default)
        edit.setValidator(QIntValidator(minimum, maximum))
        edit.textChanged.connect(lambda _text: self.option_changed.emit())
        self._add_field(label, edit)
        return edit

    def _add_text_field(self, label: str, default: str) -> QLineEdit:
        edit = styled_line_edit(default)
        edit.textChanged.connect(lambda _text: self.option_changed.emit())
        self._add_field(label, edit)
        return edit

    def set_available_layers(self, names: Sequence[str], default_name: str) -> None:
        self.layer_dropdown.set_available_layers(names, default_name)

    def get_layer_name(self) -> str:
        return self.layer_dropdown.layer_name()

    def set_layer_name(self, name: str) -> None:
        self.layer_dropdown.set_layer_name(name)

    def get_options(self) -> Any:
        return NoOptions()

    def set_options(self, options: Any) -> None:
        pass

    def has_custom_layer(self) -> bool:
        return self.get_layer_name() not in UNSET_LAYER_NAMES

    def is_modified(self) -> bool:
        return (
            self.get_options() != self.DEFAULT_OPTIONS
            or self.has_custom_layer()
            or self.selection_mode != "all"
        )
