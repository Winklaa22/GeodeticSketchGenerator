from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.title_block import SheetTitleBlockFields
from ui.editor.tabs.base import SectionWidget
from ui.widgets import SectionColumn, make_field, styled_line_edit


class SheetFieldsTab(SectionWidget):

    fieldsChanged = pyqtSignal()

    DEFAULT_FIELDS = SheetTitleBlockFields()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        column = SectionColumn(self)

        self.powiat_input = styled_line_edit("")
        column.addWidget(make_field("Powiat", self.powiat_input))

        self.gmina_input = styled_line_edit("")
        column.addWidget(make_field("Gmina", self.gmina_input))

        self.obreb_input = styled_line_edit("")
        column.addWidget(make_field("Obręb", self.obreb_input))

        self.dz_nr_input = styled_line_edit("")
        column.addWidget(make_field("Dz. nr", self.dz_nr_input))

        self.sketch_number_input = styled_line_edit("")
        column.addWidget(make_field("Szkic nr", self.sketch_number_input))

        column.addStretch(1)

        for widget in (
            self.powiat_input,
            self.gmina_input,
            self.obreb_input,
            self.dz_nr_input,
            self.sketch_number_input,
        ):
            widget.textChanged.connect(lambda _text: self.fieldsChanged.emit())

    def get_fields(self) -> SheetTitleBlockFields:
        return SheetTitleBlockFields(
            powiat=self.powiat_input.text(),
            gmina=self.gmina_input.text(),
            obreb=self.obreb_input.text(),
            dz_nr=self.dz_nr_input.text(),
            sketch_number=self.sketch_number_input.text(),
        )

    def set_fields(self, fields: SheetTitleBlockFields) -> None:
        widgets = (
            self.powiat_input,
            self.gmina_input,
            self.obreb_input,
            self.dz_nr_input,
            self.sketch_number_input,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.powiat_input.setText(fields.powiat)
        self.gmina_input.setText(fields.gmina)
        self.obreb_input.setText(fields.obreb)
        self.dz_nr_input.setText(fields.dz_nr)
        self.sketch_number_input.setText(fields.sketch_number)
        for widget in widgets:
            widget.blockSignals(False)

    def is_modified(self) -> bool:
        return self.get_fields() != self.DEFAULT_FIELDS
