from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFileDialog

from core.exceptions import ProjectFileError
from core.project import (
    TABLE_TEMPLATE_FILE_EXTENSION,
    TABLE_TEMPLATE_FILE_FILTER,
    load_table_template_file,
    save_table_template_file,
)
from core.table_template import TableTemplate
from ui.editor.table_structure_dialog import TableStructureDialog
from ui.i18n import tr

if TYPE_CHECKING:
    from ui.editor.window import MainWindow


class TableTemplateController:

    def __init__(self, host: "MainWindow") -> None:
        self._host = host

    def open_editor(self) -> None:
        dialog = TableStructureDialog(self._host.table_template, self._host)
        if dialog.exec():
            self.apply(dialog.result_template())

    def apply(self, template: TableTemplate) -> None:
        self._host.table_template = template
        self._host.refresh_table_template_bindings()
        self._host.layouts.reapply()

    def import_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._host, tr("common.import_table_template_title"), "", TABLE_TEMPLATE_FILE_FILTER
        )
        if not path:
            return
        try:
            template = load_table_template_file(path)
        except ProjectFileError as exc:
            self._host.flash_status(str(exc))
            return
        self.apply(template)
        self._host.flash_status(tr("table_template.imported_from", name=os.path.basename(path)))

    def export_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._host, tr("common.export_table_template_title"),
            "table_template" + TABLE_TEMPLATE_FILE_EXTENSION, TABLE_TEMPLATE_FILE_FILTER,
        )
        if not path:
            return
        if not path.lower().endswith(TABLE_TEMPLATE_FILE_EXTENSION):
            path += TABLE_TEMPLATE_FILE_EXTENSION
        try:
            save_table_template_file(path, self._host.table_template)
        except ProjectFileError as exc:
            self._host.flash_status(str(exc))
            return
        self._host.flash_status(tr("table_template.exported_to", name=os.path.basename(path)))
