from __future__ import annotations

import os
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtGui import QFont
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
from core.fonts import FONT_CATALOG
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
from ui.i18n import tr, tr_options
from ui.theme import SPACE_LG, SPACE_MD
from ui.theme.qt_fonts import apply_font_family
from ui.widgets import CheckField, Dropdown, SectionColumn, make_button, make_field, styled_line_edit

_ALIGN_OPTION_KEYS = [
    ("left", "table_structure.align_left"),
    ("center", "table_structure.align_center"),
    ("right", "table_structure.align_right"),
]
_VALIGN_OPTION_KEYS = [
    ("top", "table_structure.valign_top"),
    ("middle", "table_structure.valign_middle"),
    ("bottom", "table_structure.valign_bottom"),
]
_KIND_OPTION_KEYS = [
    ("static", "table_structure.kind_static"),
    ("field", "table_structure.kind_field"),
    ("image", "table_structure.kind_image"),
    ("blank", "table_structure.kind_blank"),
]
_SCOPE_OPTION_KEYS = [
    ("sheet", "table_structure.scope_sheet"),
    ("project", "table_structure.scope_project"),
]

_EDITOR_PX_PER_MM = 4.0
_REFERENCE_EDITOR_WIDTH_PX = 760
_PREVIEW_PT_PER_MM = 3.5

_PREVIEW_ALIGN_H = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}
_PREVIEW_ALIGN_V = {
    "top": Qt.AlignmentFlag.AlignTop,
    "middle": Qt.AlignmentFlag.AlignVCenter,
    "bottom": Qt.AlignmentFlag.AlignBottom,
}

# Styling applies to every selected cell; content properties stay single-cell, so a
# multi-cell selection can't accidentally stamp one label over a dozen records.
_MULTI_CELL_PROPS = frozenset({"font_id", "font_size", "bold", "italic", "align", "valign"})


def _font_option_items() -> List[Tuple[str, str]]:
    return [("", tr("table_structure.font_inherit"))] + [(spec.id, spec.label) for spec in FONT_CATALOG]


def _stamp_file_filter() -> str:
    return ";;".join((
        tr("table_structure.stamp_filter_all"),
        tr("table_structure.stamp_filter_images"),
        tr("common.dxf_filter"),
    ))


class TableStructureDialog(QDialog):

    def __init__(self, template: TableTemplate, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("table_structure.title"))
        self.resize(860, 560)
        self._template = template
        self._selected_origin: Optional[Tuple[int, int]] = None
        self._selected_origins: List[Tuple[int, int]] = []
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        outer.setSpacing(SPACE_MD)
        outer.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._grid = QTableWidget()
        self._grid.setObjectName("tableStructureGrid")
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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
        bottom.addWidget(make_button(tr("common.import"), "secondary", self._on_import))
        bottom.addWidget(make_button(tr("table_structure.export_button"), "secondary", self._on_export))
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
        toolbar.addWidget(make_button(tr("table_structure.add_row"), "secondary", self._on_add_row))
        toolbar.addWidget(make_button(tr("table_structure.delete_row"), "secondary", self._on_delete_row))
        toolbar.addWidget(make_button(tr("table_structure.add_column"), "secondary", self._on_add_column))
        toolbar.addWidget(make_button(tr("table_structure.delete_column"), "secondary", self._on_delete_column))
        self._merge_button = make_button(tr("table_structure.merge"), "secondary", self._on_merge)
        self._merge_button.setEnabled(False)
        toolbar.addWidget(self._merge_button)
        self._unmerge_button = make_button(tr("table_structure.unmerge"), "secondary", self._on_unmerge)
        self._unmerge_button.setEnabled(False)
        toolbar.addWidget(self._unmerge_button)
        toolbar.addWidget(make_button(tr("table_structure.manage_fields_button"), "secondary", self._on_manage_fields))
        toolbar.addStretch(1)
        self._table_font_dropdown = Dropdown()
        self._table_font_dropdown.set_items([(spec.id, spec.label) for spec in FONT_CATALOG])
        self._table_font_dropdown.set_current_key(self._template.default_font_id)
        self._table_font_dropdown.currentIndexChanged.connect(self._on_table_font_changed)
        toolbar.addWidget(make_field(tr("table_structure.table_font_field"), self._table_font_dropdown))
        toolbar.addWidget(make_button(tr("table_structure.clear"), "secondary", self._on_clear))
        return toolbar

    def _build_property_panel(self) -> QWidget:
        panel = QWidget()
        column = SectionColumn(panel)

        self._label_input = styled_line_edit("")
        self._label_input.editingFinished.connect(self._on_label_edited)
        column.addWidget(make_field(tr("common.label_field"), self._label_input))

        self._kind_dropdown = Dropdown()
        self._kind_dropdown.set_items(tr_options(_KIND_OPTION_KEYS))
        self._kind_dropdown.currentIndexChanged.connect(self._on_kind_changed)
        column.addWidget(make_field(tr("table_structure.kind_field_label"), self._kind_dropdown))

        self._field_dropdown = Dropdown()
        self._field_dropdown.currentIndexChanged.connect(self._on_field_changed)
        column.addWidget(make_field(tr("table_structure.field_field"), self._field_dropdown))

        stamp_row = QWidget()
        stamp_layout = QHBoxLayout(stamp_row)
        stamp_layout.setContentsMargins(0, 0, 0, 0)
        stamp_layout.setSpacing(SPACE_MD)
        self._stamp_label = QLabel(tr("table_structure.no_file_selected"))
        self._stamp_label.setWordWrap(True)
        stamp_layout.addWidget(self._stamp_label, 1)
        self._stamp_browse_button = make_button(tr("table_structure.browse"), "secondary", self._on_stamp_browse)
        stamp_layout.addWidget(self._stamp_browse_button)
        self._stamp_clear_button = make_button(tr("table_structure.clear"), "secondary", self._on_stamp_clear)
        stamp_layout.addWidget(self._stamp_clear_button)
        column.addWidget(make_field(tr("table_structure.stamp_file_field"), stamp_row))

        self._show_label_check = CheckField(tr("table_structure.show_label_checkbox"))
        self._show_label_check.toggled.connect(self._on_show_label_toggled)
        column.addWidget(self._show_label_check)

        self._align_dropdown = Dropdown()
        self._align_dropdown.set_items(tr_options(_ALIGN_OPTION_KEYS))
        self._align_dropdown.currentIndexChanged.connect(self._on_align_changed)
        column.addWidget(make_field(tr("table_structure.horizontal_align_field"), self._align_dropdown))

        self._valign_dropdown = Dropdown()
        self._valign_dropdown.set_items(tr_options(_VALIGN_OPTION_KEYS))
        self._valign_dropdown.currentIndexChanged.connect(self._on_valign_changed)
        column.addWidget(make_field(tr("table_structure.vertical_align_field"), self._valign_dropdown))

        self._font_dropdown = Dropdown()
        self._font_dropdown.set_items(_font_option_items())
        self._font_dropdown.currentIndexChanged.connect(self._on_font_changed)
        column.addWidget(make_field(tr("table_structure.font_field"), self._font_dropdown))

        self._bold_check = CheckField(tr("table_structure.bold"))
        self._bold_check.toggled.connect(self._on_bold_toggled)
        column.addWidget(self._bold_check)

        self._italic_check = CheckField(tr("table_structure.italic"))
        self._italic_check.toggled.connect(self._on_italic_toggled)
        column.addWidget(self._italic_check)

        self._font_size_input = QDoubleSpinBox()
        self._font_size_input.setRange(0.5, 20.0)
        self._font_size_input.setSingleStep(0.1)
        self._font_size_input.setSuffix(tr("table_structure.mm_suffix"))
        self._font_size_input.valueChanged.connect(self._on_font_size_changed)
        column.addWidget(make_field(tr("table_structure.font_size_field"), self._font_size_input))

        column.addStretch(1)
        self._set_property_panel_enabled(False)
        return panel

    def _preview_font(self, cell: CellDef) -> QFont:
        font = apply_font_family(QFont(), cell.font_id or self._template.default_font_id)
        font.setPointSizeF(max(cell.font_size * _PREVIEW_PT_PER_MM, 6.0))
        font.setBold(cell.bold)
        font.setItalic(cell.italic)
        return font

    @staticmethod
    def _cell_display_text(cell: CellDef) -> str:
        if cell.kind == "blank":
            return ""
        if cell.kind == "field":
            return f"[{cell.field_name}]" if cell.field_name else tr("table_structure.placeholder_field")
        if cell.kind == "image":
            if cell.image_path:
                return tr("table_structure.placeholder_stamp_named", name=os.path.basename(cell.image_path))
            return tr("table_structure.placeholder_stamp")
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
                item.setFont(self._preview_font(cell))
                item.setTextAlignment(
                    _PREVIEW_ALIGN_H.get(cell.align, Qt.AlignmentFlag.AlignLeft)
                    | _PREVIEW_ALIGN_V.get(cell.valign, Qt.AlignmentFlag.AlignTop)
                )
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
        self._clear_selection_state()
        self._rebuild_grid()

    def _on_add_column(self) -> None:
        at_index = self._selected_origin[1] + 1 if self._selected_origin else len(self._template.columns)
        self._template = add_column(self._template, at_index)
        self._rebuild_grid()

    def _on_delete_column(self) -> None:
        if self._selected_origin is None:
            return
        self._template = delete_column(self._template, self._selected_origin[1])
        self._clear_selection_state()
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
        self._selected_origins = [self._selected_origin]
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

    def _on_clear(self) -> None:
        if not self._template.rows and not self._template.columns:
            return
        confirmed = QMessageBox.question(
            self, tr("table_structure.clear_table_title"), tr("table_structure.clear_table_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._template = TableTemplate(columns=[], rows=[], cells=[])
        self._clear_selection_state()
        self._rebuild_grid()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        cell = find_cell_at(self._template, item.row(), item.column())
        if cell is None or cell.kind != "static":
            return
        self._template = set_cell(self._template, cell.row, cell.col, label=item.text())

    def _clear_selection_state(self) -> None:
        self._selected_origin = None
        self._selected_origins = []

    def _selected_cells(self) -> List[CellDef]:
        found: Dict[Tuple[int, int], CellDef] = {}
        for selected in self._grid.selectedRanges():
            for row in range(selected.topRow(), selected.bottomRow() + 1):
                for col in range(selected.leftColumn(), selected.rightColumn() + 1):
                    cell = find_cell_at(self._template, row, col)
                    if cell is not None:
                        found[(cell.row, cell.col)] = cell
        return list(found.values())

    def _on_selection_changed(self) -> None:
        if self._updating:
            return
        cells = self._selected_cells()
        self._selected_origins = [(cell.row, cell.col) for cell in cells]
        self._selected_origin = self._selected_origins[0] if self._selected_origins else None
        self._sync_property_panel(cells)
        ranges = self._grid.selectedRanges()
        single_range = len(ranges) == 1
        self._merge_button.setEnabled(
            single_range and (ranges[0].rowCount() > 1 or ranges[0].columnCount() > 1)
        )
        primary = cells[0] if cells else None
        self._unmerge_button.setEnabled(
            len(cells) == 1 and primary is not None and (primary.row_span > 1 or primary.col_span > 1)
        )

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

    def _sync_property_panel(self, cells: List[CellDef]) -> None:
        self._updating = True
        try:
            if not cells:
                self._label_input.setText("")
                self._stamp_label.setText(tr("table_structure.no_file_selected"))
                self._stamp_label.setToolTip("")
                self._set_property_panel_enabled(False)
                return
            cell = cells[0]
            single = len(cells) == 1
            self._set_property_panel_enabled(True)
            self._set_content_widgets_enabled(single)
            self._label_input.setText(cell.label if single else "")
            self._kind_dropdown.set_current_key(cell.kind)
            self._refresh_field_dropdown_items()
            self._field_dropdown.set_current_key(cell.field_name)
            self._field_dropdown.setEnabled(single and cell.kind == "field")
            stamp_name = os.path.basename(cell.image_path) if cell.image_path else tr("table_structure.no_file_selected")
            self._stamp_label.setText(stamp_name if single else tr("table_structure.no_file_selected"))
            self._stamp_label.setToolTip(cell.image_path if single else "")
            self._stamp_browse_button.setEnabled(single and cell.kind == "image")
            self._stamp_clear_button.setEnabled(single and cell.kind == "image" and bool(cell.image_path))
            self._show_label_check.setChecked(cell.show_label)
            self._align_dropdown.set_current_key(cell.align)
            self._valign_dropdown.set_current_key(cell.valign)
            self._font_dropdown.set_current_key(cell.font_id)
            self._bold_check.setChecked(cell.bold)
            self._italic_check.setChecked(cell.italic)
            self._font_size_input.setValue(cell.font_size)
        finally:
            self._updating = False

    def _set_content_widgets_enabled(self, enabled: bool) -> None:
        for widget in (self._label_input, self._kind_dropdown, self._show_label_check):
            widget.setEnabled(enabled)

    def _set_property_panel_enabled(self, enabled: bool) -> None:
        for widget in (
            self._label_input, self._kind_dropdown, self._field_dropdown, self._show_label_check,
            self._align_dropdown, self._valign_dropdown, self._font_dropdown, self._bold_check,
            self._italic_check, self._font_size_input, self._stamp_browse_button,
            self._stamp_clear_button,
        ):
            widget.setEnabled(enabled)

    def _apply_property_change(self, **changes) -> None:
        if self._updating or not self._selected_origins:
            return
        fans_out = _MULTI_CELL_PROPS.issuperset(changes)
        targets = list(self._selected_origins) if fans_out else self._selected_origins[:1]
        for row, col in targets:
            self._template = set_cell(self._template, row, col, **changes)
        self._rebuild_grid()
        self._reselect(targets)

    def _reselect(self, origins: List[Tuple[int, int]]) -> None:
        self._updating = True
        self._grid.clearSelection()
        for row, col in origins:
            item = self._grid.item(row, col)
            if item is not None:
                item.setSelected(True)
        if origins:
            self._grid.setCurrentCell(
                origins[0][0], origins[0][1], QItemSelectionModel.SelectionFlag.NoUpdate
            )
        self._updating = False
        self._selected_origins = list(origins)
        self._selected_origin = origins[0] if origins else None
        cells = [find_cell_at(self._template, row, col) for row, col in origins]
        self._sync_property_panel([cell for cell in cells if cell is not None])

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
        path, _ = QFileDialog.getOpenFileName(self, tr("table_structure.choose_stamp_title"), "", _stamp_file_filter())
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

    def _on_font_changed(self, _index: int) -> None:
        if self._updating:
            return
        self._apply_property_change(font_id=self._font_dropdown.current_key())

    def _on_table_font_changed(self, _index: int) -> None:
        if self._updating:
            return
        font_id = self._table_font_dropdown.current_key()
        if not font_id:
            return
        self._template = replace(self._template, default_font_id=font_id)
        self._rebuild_grid()
        self._reselect(list(self._selected_origins))

    def _on_bold_toggled(self, checked: bool) -> None:
        self._apply_property_change(bold=checked)

    def _on_italic_toggled(self, checked: bool) -> None:
        self._apply_property_change(italic=checked)

    def _on_font_size_changed(self, value: float) -> None:
        self._apply_property_change(font_size=value)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("common.import_table_template_title"), "", TABLE_TEMPLATE_FILE_FILTER
        )
        if not path:
            return
        try:
            self._template = load_table_template_file(path)
        except ProjectFileError as exc:
            QMessageBox.warning(self, tr("common.import_table_template_title"), str(exc))
            return
        self._clear_selection_state()
        self._table_font_dropdown.set_current_key(self._template.default_font_id)
        self._rebuild_grid()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("common.export_table_template_title"),
            "table_template" + TABLE_TEMPLATE_FILE_EXTENSION, TABLE_TEMPLATE_FILE_FILTER,
        )
        if not path:
            return
        if not path.lower().endswith(TABLE_TEMPLATE_FILE_EXTENSION):
            path += TABLE_TEMPLATE_FILE_EXTENSION
        try:
            save_table_template_file(path, self._template)
        except ProjectFileError as exc:
            QMessageBox.warning(self, tr("common.export_table_template_title"), str(exc))


class _ManageFieldsDialog(QDialog):

    def __init__(self, template: TableTemplate, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("common.manage_fields_title"))
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
        self._scope_dropdown.set_items(tr_options(_SCOPE_OPTION_KEYS))
        form_row.addWidget(make_field(tr("table_structure.name_field"), self._name_input))
        form_row.addWidget(make_field(tr("common.label_field"), self._label_input))
        form_row.addWidget(make_field(tr("table_structure.scope_field"), self._scope_dropdown))
        column.addLayout(form_row)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(make_button(tr("table_structure.add_field_button"), "secondary", self._on_add))
        self._update_button = make_button(
            tr("table_structure.update_selected_button"), "secondary", self._on_update
        )
        self._update_button.setEnabled(False)
        buttons_row.addWidget(self._update_button)
        self._delete_button = make_button(
            tr("table_structure.delete_selected_button"), "secondary", self._on_delete
        )
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
            scope_text = (
                tr("table_structure.per_sheet_lower") if field_def.scope == "sheet"
                else tr("table_structure.per_project_lower")
            )
            item = QListWidgetItem(
                tr(
                    "table_structure.field_list_item",
                    label=field_def.label or field_def.name, name=field_def.name, scope=scope_text,
                )
            )
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
            QMessageBox.warning(self, tr("common.manage_fields_title"), str(exc))
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
            QMessageBox.warning(self, tr("common.manage_fields_title"), str(exc))
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
            self, tr("table_structure.delete_field_title"), tr("table_structure.delete_field_message", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._template = remove_field(self._template, name)
        self._rebuild_list()
        self._clear_form()
