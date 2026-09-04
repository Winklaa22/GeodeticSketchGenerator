from __future__ import annotations

import os
from dataclasses import replace
from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import ProjectFileError
from core.project import (
    TABLE_TEMPLATE_FILE_EXTENSION,
    TABLE_TEMPLATE_FILE_FILTER,
    load_table_template_file,
    save_table_template_file,
)
from core.table_template import (
    CellDef,
    ColumnDef,
    FieldDef,
    TableTemplate,
    add_column,
    add_field,
    add_row,
    delete_column,
    delete_row,
    find_cell_at,
    merge_cells,
    remove_field,
    rename_field,
    resize_row,
    set_cell,
    unmerge_cell,
    update_field,
)
from ui.theme import SPACE_LG, SPACE_MD
from ui.widgets import CheckField, Dropdown, SectionColumn, make_button, make_field, styled_line_edit

_ALIGN_OPTIONS = [("left", "Left"), ("center", "Center"), ("right", "Right")]
_VALIGN_OPTIONS = [("top", "Top"), ("middle", "Middle"), ("bottom", "Bottom")]
_KIND_OPTIONS = [("static", "Static text"), ("field", "Field"), ("image", "Stamp (image/DXF)"), ("blank", "Blank")]
_SCOPE_OPTIONS = [("sheet", "Per sheet"), ("project", "Per project")]
_STAMP_FILE_FILTER = "Images and DXF Files (*.png *.jpg *.jpeg *.bmp *.gif *.dxf);;Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;DXF Files (*.dxf)"

_EDITOR_PX_PER_MM = 4.0
_REFERENCE_EDITOR_WIDTH_PX = 760


class TableStructureDialog(QDialog):

    def __init__(self, template: TableTemplate, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Table Structure")
        self.resize(860, 560)
        self._template = template
        self._selected_origin: Optional[Tuple[int, int]] = None
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        outer.setSpacing(SPACE_MD)
        outer.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._grid = QTableWidget()
        self._grid.setObjectName("tableStructureGrid")
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self._grid.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._grid.itemChanged.connect(self._on_item_changed)
        self._grid.itemSelectionChanged.connect(self._on_selection_changed)
        self._grid.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self._grid.verticalHeader().sectionResized.connect(self._on_row_resized)
        splitter.addWidget(self._grid)
        splitter.addWidget(self._build_property_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(make_button("Import…", "secondary", self._on_import))
        bottom.addWidget(make_button("Export…", "secondary", self._on_export))
        bottom.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

        self._rebuild_grid()

    def result_template(self) -> TableTemplate:
        return self._template

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.addWidget(make_button("Add row", "secondary", self._on_add_row))
        toolbar.addWidget(make_button("Delete row", "secondary", self._on_delete_row))
        toolbar.addWidget(make_button("Add column", "secondary", self._on_add_column))
        toolbar.addWidget(make_button("Delete column", "secondary", self._on_delete_column))
        self._merge_button = make_button("Merge", "secondary", self._on_merge)
        self._merge_button.setEnabled(False)
        toolbar.addWidget(self._merge_button)
        self._unmerge_button = make_button("Unmerge", "secondary", self._on_unmerge)
        self._unmerge_button.setEnabled(False)
        toolbar.addWidget(self._unmerge_button)
        toolbar.addWidget(make_button("Manage fields…", "secondary", self._on_manage_fields))
        toolbar.addStretch(1)
        return toolbar

    def _build_property_panel(self) -> QWidget:
        panel = QWidget()
        column = SectionColumn(panel)

        self._label_input = styled_line_edit("")
        self._label_input.editingFinished.connect(self._on_label_edited)
        column.addWidget(make_field("Label", self._label_input))

        self._kind_dropdown = Dropdown()
        self._kind_dropdown.set_items(_KIND_OPTIONS)
        self._kind_dropdown.currentIndexChanged.connect(self._on_kind_changed)
        column.addWidget(make_field("Kind", self._kind_dropdown))

        self._field_dropdown = Dropdown()
        self._field_dropdown.currentIndexChanged.connect(self._on_field_changed)
        column.addWidget(make_field("Field", self._field_dropdown))

        stamp_row = QWidget()
        stamp_layout = QHBoxLayout(stamp_row)
        stamp_layout.setContentsMargins(0, 0, 0, 0)
        stamp_layout.setSpacing(SPACE_MD)
        self._stamp_label = QLabel("No file selected")
        self._stamp_label.setWordWrap(True)
        stamp_layout.addWidget(self._stamp_label, 1)
        self._stamp_browse_button = make_button("Browse…", "secondary", self._on_stamp_browse)
        stamp_layout.addWidget(self._stamp_browse_button)
        self._stamp_clear_button = make_button("Clear", "secondary", self._on_stamp_clear)
        stamp_layout.addWidget(self._stamp_clear_button)
        column.addWidget(make_field("Stamp file", stamp_row))

        self._show_label_check = CheckField("Show label before value")
        self._show_label_check.toggled.connect(self._on_show_label_toggled)
        column.addWidget(self._show_label_check)

        self._align_dropdown = Dropdown()
        self._align_dropdown.set_items(_ALIGN_OPTIONS)
        self._align_dropdown.currentIndexChanged.connect(self._on_align_changed)
        column.addWidget(make_field("Horizontal align", self._align_dropdown))

        self._valign_dropdown = Dropdown()
        self._valign_dropdown.set_items(_VALIGN_OPTIONS)
        self._valign_dropdown.currentIndexChanged.connect(self._on_valign_changed)
        column.addWidget(make_field("Vertical align", self._valign_dropdown))

        self._bold_check = CheckField("Bold")
        self._bold_check.toggled.connect(self._on_bold_toggled)
        column.addWidget(self._bold_check)

        self._italic_check = CheckField("Italic")
        self._italic_check.toggled.connect(self._on_italic_toggled)
        column.addWidget(self._italic_check)

        self._font_size_input = QDoubleSpinBox()
        self._font_size_input.setRange(0.5, 20.0)
        self._font_size_input.setSingleStep(0.1)
        self._font_size_input.setSuffix(" mm")
        self._font_size_input.valueChanged.connect(self._on_font_size_changed)
        column.addWidget(make_field("Font size", self._font_size_input))

        column.addStretch(1)
        self._set_property_panel_enabled(False)
        return panel

    @staticmethod
    def _cell_display_text(cell: CellDef) -> str:
        if cell.kind == "blank":
            return ""
        if cell.kind == "field":
            return f"[{cell.field_name}]" if cell.field_name else "[field]"
        if cell.kind == "image":
            return f"[stamp: {os.path.basename(cell.image_path)}]" if cell.image_path else "[stamp]"
        return cell.label

    def _rebuild_grid(self) -> None:
        self._updating = True
        try:
            self._grid.clearContents()
            self._grid.clearSpans()
            self._grid.setRowCount(len(self._template.rows))
            self._grid.setColumnCount(len(self._template.columns))
            for row_index, row_def in enumerate(self._template.rows):
                self._grid.setRowHeight(row_index, max(int(row_def.height_mm * _EDITOR_PX_PER_MM), 18))
            total_fraction = sum(c.width_fraction for c in self._template.columns) or 1.0
            for col_index, col_def in enumerate(self._template.columns):
                width = col_def.width_fraction / total_fraction * _REFERENCE_EDITOR_WIDTH_PX
                self._grid.setColumnWidth(col_index, max(int(width), 40))
            for cell in self._template.cells:
                item = QTableWidgetItem(self._cell_display_text(cell))
                flags = item.flags()
                if cell.kind == "static":
                    flags |= Qt.ItemFlag.ItemIsEditable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags)
                self._grid.setItem(cell.row, cell.col, item)
                if cell.row_span > 1 or cell.col_span > 1:
                    self._grid.setSpan(cell.row, cell.col, cell.row_span, cell.col_span)
            self._refresh_field_dropdown_items()
        finally:
            self._updating = False

    def _refresh_field_dropdown_items(self) -> None:
        items = [(f.name, f.label or f.name) for f in self._template.fields]
        self._field_dropdown.set_items(items)

    def _on_add_row(self) -> None:
        at_index = self._selected_origin[0] + 1 if self._selected_origin else len(self._template.rows)
        self._template = add_row(self._template, at_index)
        self._rebuild_grid()

    def _on_delete_row(self) -> None:
        if self._selected_origin is None:
            return
        self._template = delete_row(self._template, self._selected_origin[0])
        self._selected_origin = None
        self._rebuild_grid()

    def _on_add_column(self) -> None:
        at_index = self._selected_origin[1] + 1 if self._selected_origin else len(self._template.columns)
        self._template = add_column(self._template, at_index)
        self._rebuild_grid()

    def _on_delete_column(self) -> None:
        if self._selected_origin is None:
            return
        self._template = delete_column(self._template, self._selected_origin[1])
        self._selected_origin = None
        self._rebuild_grid()

    def _on_merge(self) -> None:
        ranges = self._grid.selectedRanges()
        if not ranges:
            return
        selected = ranges[0]
        self._template = merge_cells(
            self._template, selected.topRow(), selected.leftColumn(),
            selected.rowCount(), selected.columnCount(),
        )
        self._selected_origin = (selected.topRow(), selected.leftColumn())
        self._rebuild_grid()

    def _on_unmerge(self) -> None:
        if self._selected_origin is None:
            return
        self._template = unmerge_cell(self._template, *self._selected_origin)
        self._rebuild_grid()

    def _on_manage_fields(self) -> None:
        dialog = _ManageFieldsDialog(self._template, self)
        dialog.exec()
        self._template = dialog.result_template()
        self._rebuild_grid()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        cell = find_cell_at(self._template, item.row(), item.column())
        if cell is None or cell.kind != "static":
            return
        self._template = set_cell(self._template, cell.row, cell.col, label=item.text())

    def _on_selection_changed(self) -> None:
        if self._updating:
            return
        ranges = self._grid.selectedRanges()
        if len(ranges) != 1:
            self._selected_origin = None
            self._sync_property_panel(None)
            self._merge_button.setEnabled(False)
            self._unmerge_button.setEnabled(False)
            return
        selected = ranges[0]
        cell = find_cell_at(self._template, selected.topRow(), selected.leftColumn())
        self._selected_origin = (cell.row, cell.col) if cell is not None else None
        self._sync_property_panel(cell)
        self._merge_button.setEnabled(selected.rowCount() > 1 or selected.columnCount() > 1)
        self._unmerge_button.setEnabled(cell is not None and (cell.row_span > 1 or cell.col_span > 1))

    def _on_row_resized(self, index: int, _old_size: int, new_size: int) -> None:
        if self._updating:
            return
        self._template = resize_row(self._template, index, max(new_size / _EDITOR_PX_PER_MM, 0.5))

    def _on_column_resized(self, _index: int, _old_size: int, _new_size: int) -> None:
        if self._updating:
            return
        widths = [self._grid.columnWidth(i) for i in range(self._grid.columnCount())]
        total = sum(widths) or 1.0
        self._template = replace(self._template, columns=[ColumnDef(width_fraction=w / total) for w in widths])

    def _sync_property_panel(self, cell: Optional[CellDef]) -> None:
        self._updating = True
        try:
            if cell is None:
                self._label_input.setText("")
                self._stamp_label.setText("No file selected")
                self._stamp_label.setToolTip("")
                self._set_property_panel_enabled(False)
                return
            self._set_property_panel_enabled(True)
            self._label_input.setText(cell.label)
            self._kind_dropdown.set_current_key(cell.kind)
            self._refresh_field_dropdown_items()
            self._field_dropdown.set_current_key(cell.field_name)
            self._field_dropdown.setEnabled(cell.kind == "field")
            self._stamp_label.setText(os.path.basename(cell.image_path) if cell.image_path else "No file selected")
            self._stamp_label.setToolTip(cell.image_path)
            self._stamp_browse_button.setEnabled(cell.kind == "image")
            self._stamp_clear_button.setEnabled(cell.kind == "image" and bool(cell.image_path))
            self._show_label_check.setChecked(cell.show_label)
            self._align_dropdown.set_current_key(cell.align)
            self._valign_dropdown.set_current_key(cell.valign)
            self._bold_check.setChecked(cell.bold)
            self._italic_check.setChecked(cell.italic)
            self._font_size_input.setValue(cell.font_size)
        finally:
            self._updating = False

    def _set_property_panel_enabled(self, enabled: bool) -> None:
        for widget in (
            self._label_input, self._kind_dropdown, self._field_dropdown, self._show_label_check,
            self._align_dropdown, self._valign_dropdown, self._bold_check, self._italic_check,
            self._font_size_input, self._stamp_browse_button, self._stamp_clear_button,
        ):
            widget.setEnabled(enabled)

    def _apply_property_change(self, **changes) -> None:
        if self._updating or self._selected_origin is None:
            return
        row, col = self._selected_origin
        self._template = set_cell(self._template, row, col, **changes)
        self._rebuild_grid()
        self._reselect(row, col)

    def _reselect(self, row: int, col: int) -> None:
        self._updating = True
        self._grid.setCurrentCell(row, col)
        self._updating = False
        self._selected_origin = (row, col)
        self._sync_property_panel(find_cell_at(self._template, row, col))

    def _on_label_edited(self) -> None:
        self._apply_property_change(label=self._label_input.text())

    def _on_kind_changed(self, _index: int) -> None:
        kind = self._kind_dropdown.current_key()
        if kind:
            self._apply_property_change(kind=kind)

    def _on_field_changed(self, _index: int) -> None:
        name = self._field_dropdown.current_key()
        if name:
            self._apply_property_change(field_name=name)

    def _on_stamp_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Stamp File", "", _STAMP_FILE_FILTER)
        if path:
            self._apply_property_change(image_path=path)

    def _on_stamp_clear(self) -> None:
        self._apply_property_change(image_path="")

    def _on_show_label_toggled(self, checked: bool) -> None:
        self._apply_property_change(show_label=checked)

    def _on_align_changed(self, _index: int) -> None:
        key = self._align_dropdown.current_key()
        if key:
            self._apply_property_change(align=key)

    def _on_valign_changed(self, _index: int) -> None:
        key = self._valign_dropdown.current_key()
        if key:
            self._apply_property_change(valign=key)

    def _on_bold_toggled(self, checked: bool) -> None:
        self._apply_property_change(bold=checked)

    def _on_italic_toggled(self, checked: bool) -> None:
        self._apply_property_change(italic=checked)

    def _on_font_size_changed(self, value: float) -> None:
        self._apply_property_change(font_size=value)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Table Template", "", TABLE_TEMPLATE_FILE_FILTER)
        if not path:
            return
        try:
            self._template = load_table_template_file(path)
        except ProjectFileError as exc:
            QMessageBox.warning(self, "Import Table Template", str(exc))
            return
        self._selected_origin = None
        self._rebuild_grid()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Table Template", "table_template" + TABLE_TEMPLATE_FILE_EXTENSION,
            TABLE_TEMPLATE_FILE_FILTER,
        )
        if not path:
            return
        if not path.lower().endswith(TABLE_TEMPLATE_FILE_EXTENSION):
            path += TABLE_TEMPLATE_FILE_EXTENSION
        try:
            save_table_template_file(path, self._template)
        except ProjectFileError as exc:
            QMessageBox.warning(self, "Export Table Template", str(exc))


class _ManageFieldsDialog(QDialog):

    def __init__(self, template: TableTemplate, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Fields")
        self.resize(420, 420)
        self._template = template
        self._editing_name: Optional[str] = None

        column = SectionColumn(self)
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        column.addWidget(self._list)

        form_row = QHBoxLayout()
        self._name_input = styled_line_edit("")
        self._label_input = styled_line_edit("")
        self._scope_dropdown = Dropdown()
        self._scope_dropdown.set_items(_SCOPE_OPTIONS)
        form_row.addWidget(make_field("Name", self._name_input))
        form_row.addWidget(make_field("Label", self._label_input))
        form_row.addWidget(make_field("Scope", self._scope_dropdown))
        column.addLayout(form_row)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(make_button("Add field", "secondary", self._on_add))
        self._update_button = make_button("Update selected", "secondary", self._on_update)
        self._update_button.setEnabled(False)
        buttons_row.addWidget(self._update_button)
        self._delete_button = make_button("Delete selected", "secondary", self._on_delete)
        self._delete_button.setEnabled(False)
        buttons_row.addWidget(self._delete_button)
        column.addLayout(buttons_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        column.addWidget(buttons)

        self._rebuild_list()

    def result_template(self) -> TableTemplate:
        return self._template

    def _rebuild_list(self) -> None:
        self._list.clear()
        for field_def in self._template.fields:
            scope_text = "per sheet" if field_def.scope == "sheet" else "per project"
            item = QListWidgetItem(f"{field_def.label or field_def.name}  ({field_def.name}, {scope_text})")
            item.setData(Qt.ItemDataRole.UserRole, field_def.name)
            self._list.addItem(item)

    def _select_by_name(self, name: str) -> None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self._list.setCurrentItem(item)
                return

    def _clear_form(self) -> None:
        self._editing_name = None
        self._name_input.clear()
        self._label_input.clear()
        self._update_button.setEnabled(False)
        self._delete_button.setEnabled(False)

    def _on_selection_changed(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self._clear_form()
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        field_def = next((f for f in self._template.fields if f.name == name), None)
        if field_def is None:
            self._clear_form()
            return
        self._editing_name = field_def.name
        self._name_input.setText(field_def.name)
        self._label_input.setText(field_def.label)
        self._scope_dropdown.set_current_key(field_def.scope)
        self._update_button.setEnabled(True)
        self._delete_button.setEnabled(True)

    def _on_add(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            return
        label = self._label_input.text().strip() or name
        scope = self._scope_dropdown.current_key() or "sheet"
        try:
            self._template = add_field(self._template, FieldDef(name=name, label=label, scope=scope))
        except ValueError as exc:
            QMessageBox.warning(self, "Manage Fields", str(exc))
            return
        self._rebuild_list()
        self._clear_form()

    def _on_update(self) -> None:
        if self._editing_name is None:
            return
        new_name = self._name_input.text().strip()
        if not new_name:
            return
        label = self._label_input.text().strip() or new_name
        scope = self._scope_dropdown.current_key() or "sheet"
        try:
            if new_name != self._editing_name:
                self._template = rename_field(self._template, self._editing_name, new_name)
            self._template = update_field(self._template, new_name, label=label, scope=scope)
        except ValueError as exc:
            QMessageBox.warning(self, "Manage Fields", str(exc))
            return
        self._editing_name = new_name
        self._rebuild_list()
        self._select_by_name(new_name)

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        confirmed = QMessageBox.question(
            self, "Delete field", f'Delete field "{name}"? Cells using it become blank.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._template = remove_field(self._template, name)
        self._rebuild_list()
        self._clear_form()
