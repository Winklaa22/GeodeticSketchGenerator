from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from ui.dxf.sheet_tabs import SheetList
from ui.editor.tabs.base import SectionWidget
from ui.editor.tabs.dynamic_fields_tab import DynamicFieldsTab
from ui.editor.tabs.plot_tab import PlotTab
from ui.theme import SPACE_LG, SPACE_SM
from ui.widgets import Accordion, AccordionSection, make_button


class _SheetsSection(SectionWidget):

    activated = pyqtSignal(int)
    addRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()
    renameRequested = pyqtSignal()
    deleteRequested = pyqtSignal()
    moveUpRequested = pyqtSignal()
    moveDownRequested = pyqtSignal()
    exportAllRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_LG)

        self.sheet_list = SheetList()
        self.sheet_list.activated.connect(self.activated.emit)
        layout.addWidget(self.sheet_list)

        grid = QGridLayout()
        grid.setSpacing(SPACE_SM)
        self._add_button = make_button("Add", "secondary", lambda: self.addRequested.emit())
        self._duplicate_button = make_button(
            "Duplicate", "secondary", lambda: self.duplicateRequested.emit()
        )
        self._rename_button = make_button("Rename", "secondary", lambda: self.renameRequested.emit())
        self._delete_button = make_button("Delete", "secondary", lambda: self.deleteRequested.emit())
        self._up_button = make_button("Move up", "secondary", lambda: self.moveUpRequested.emit())
        self._down_button = make_button(
            "Move down", "secondary", lambda: self.moveDownRequested.emit()
        )
        grid.addWidget(self._add_button, 0, 0)
        grid.addWidget(self._duplicate_button, 0, 1)
        grid.addWidget(self._rename_button, 1, 0)
        grid.addWidget(self._delete_button, 1, 1)
        grid.addWidget(self._up_button, 2, 0)
        grid.addWidget(self._down_button, 2, 1)
        layout.addLayout(grid)

        self.export_all_button = make_button(
            "Export all sheets to one PDF", "primary", lambda: self.exportAllRequested.emit()
        )
        layout.addWidget(self.export_all_button)

    def refresh(self, names: Sequence[str], active: Optional[int], has_document: bool) -> None:
        self.sheet_list.refresh(names, active)
        selected = active is not None
        self._duplicate_button.setEnabled(selected)
        self._rename_button.setEnabled(selected)
        self._delete_button.setEnabled(selected)
        self._up_button.setEnabled(selected and active > 0)
        self._down_button.setEnabled(selected and active < len(names) - 1)
        self.export_all_button.setEnabled(has_document and bool(names))


class LayoutPanel(QWidget):

    sheetActivated = pyqtSignal(int)
    addRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()
    renameRequested = pyqtSignal()
    deleteRequested = pyqtSignal()
    moveUpRequested = pyqtSignal()
    moveDownRequested = pyqtSignal()
    exportAllRequested = pyqtSignal()
    optionsChanged = pyqtSignal()
    projectFieldsChanged = pyqtSignal()
    exportRequested = pyqtSignal()
    centerRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.sheets_section = _SheetsSection()
        self.plot_tab = PlotTab()
        self.sheet_fields_tab = DynamicFieldsTab()
        self.project_fields_tab = DynamicFieldsTab()

        self.accordion = Accordion()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.accordion)

        self.accordion.add_section(
            AccordionSection("sheets_section", "Sheets", self.sheets_section)
        )
        self._fields_section = AccordionSection(
            "sheet_fields_section", "Sheet details", self.sheet_fields_tab
        )
        self.accordion.add_section(self._fields_section)
        self._project_fields_section = AccordionSection(
            "project_fields_section", "Project fields", self.project_fields_tab
        )
        self.accordion.add_section(self._project_fields_section)
        self._page_section = AccordionSection(
            "page_setup_section", "Page setup", self.plot_tab
        )
        self.accordion.add_section(self._page_section)

        self.sheets_section.activated.connect(self.sheetActivated.emit)
        self.sheets_section.addRequested.connect(self.addRequested.emit)
        self.sheets_section.duplicateRequested.connect(self.duplicateRequested.emit)
        self.sheets_section.renameRequested.connect(self.renameRequested.emit)
        self.sheets_section.deleteRequested.connect(self.deleteRequested.emit)
        self.sheets_section.moveUpRequested.connect(self.moveUpRequested.emit)
        self.sheets_section.moveDownRequested.connect(self.moveDownRequested.emit)
        self.sheets_section.exportAllRequested.connect(self.exportAllRequested.emit)
        self.sheet_fields_tab.fieldsChanged.connect(self.optionsChanged.emit)
        self.project_fields_tab.fieldsChanged.connect(self.projectFieldsChanged.emit)
        self.plot_tab.optionsChanged.connect(self.optionsChanged.emit)
        self.plot_tab.exportRequested.connect(self.exportRequested.emit)
        self.plot_tab.centerRequested.connect(self.centerRequested.emit)

    def refresh(self, names: Sequence[str], active: Optional[int], has_document: bool) -> None:
        self.sheets_section.refresh(names, active, has_document)
        self.sheet_fields_tab.setEnabled(active is not None)
        self.plot_tab.setEnabled(active is not None)
        self.plot_tab.set_export_enabled(has_document and active is not None)

    def set_coverage_text(self, text: str) -> None:
        self.plot_tab.set_coverage_text(text)
