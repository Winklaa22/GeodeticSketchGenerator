from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QLineEdit, QWidget

from core.table_template import FieldDef
from ui.editor.tabs.base import SectionWidget
from ui.i18n import tr
from ui.widgets import SectionColumn, make_field, styled_line_edit


class DynamicFieldsTab(SectionWidget):

    fieldsChanged = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._column = SectionColumn(self)
        self._inputs: Dict[str, QLineEdit] = {}
        self._placeholder = QLabel(tr("tabs.no_fields_defined"))
        self._placeholder.setObjectName("fieldLabel")
        self._show_placeholder()

    def _clear_column(self) -> None:
        while self._column.count():
            item = self._column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _show_placeholder(self) -> None:
        self._clear_column()
        self._column.addWidget(self._placeholder)
        self._column.addStretch(1)

    def rebuild(self, field_defs: List[FieldDef]) -> None:
        self._clear_column()
        self._inputs = {}
        if not field_defs:
            self._show_placeholder()
            return
        for field_def in field_defs:
            edit = styled_line_edit("")
            edit.textChanged.connect(self._on_text_changed)
            self._inputs[field_def.name] = edit
            self._column.addWidget(make_field(field_def.label or field_def.name, edit))
        self._column.addStretch(1)

    def _on_text_changed(self, _text: str) -> None:
        self.fieldsChanged.emit()

    def get_values(self) -> Dict[str, str]:
        return {name: edit.text() for name, edit in self._inputs.items()}

    def set_values(self, values: Dict[str, str]) -> None:
        for edit in self._inputs.values():
            edit.blockSignals(True)
        try:
            for name, edit in self._inputs.items():
                edit.setText(values.get(name, ""))
        finally:
            for edit in self._inputs.values():
                edit.blockSignals(False)

    def is_modified(self) -> bool:
        return any(edit.text() for edit in self._inputs.values())
