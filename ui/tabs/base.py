from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QLineEdit, QWidget

from ui.widgets import (
    CheckField,
    LayerDropdown,
    SectionColumn,
    decimal_validator,
    make_field,
    styled_line_edit,
)

DEFAULT_LAYER_NAME = "0"
UNSET_LAYER_NAMES = ("", DEFAULT_LAYER_NAME)


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
        self.layer_dropdown = LayerDropdown()
        self.layer_dropdown.layerChanged.connect(self.option_changed.emit)
        self._column.addWidget(make_field("Layer", self.layer_dropdown))
        self._column.addStretch(1)

    def _build_fields(self) -> None:
        pass

    def _add_widget(self, widget: QWidget) -> QWidget:
        self._column.addWidget(widget)
        return widget

    def _add_field(self, label: str, widget: QWidget) -> QWidget:
        self._column.addWidget(make_field(label, widget))
        return widget

    def _add_check_field(self, label: str) -> CheckField:
        checkbox = CheckField(label)
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
        return self.get_options() != self.DEFAULT_OPTIONS or self.has_custom_layer()
