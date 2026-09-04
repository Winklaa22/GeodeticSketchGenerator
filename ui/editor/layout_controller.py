from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, List, Optional, Tuple

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from ezdxf.math import Vec2

from core.plot import (
    PlotOptions,
    resolved_options,
    rotated_bbox_extents,
    scale_label,
    sheet_label,
    units_per_mm,
)
from core.sheets import Sheet
from core.table_template import MAX_TABLE_WIDTH_MM, Rect, table_layout
from ui.dxf.page_frame import PageFrame, page_frame_for
from ui.dxf.pdf_export import PlotJob

if TYPE_CHECKING:
    from ui.editor.window import MainWindow


class LayoutController:

    def __init__(self, host: "MainWindow") -> None:
        self._host = host
        self._syncing = False
        self._tab_signature: Optional[Tuple[Tuple[str, ...], Optional[int]]] = None

    @property
    def _sheets(self):
        return self._host.sheets

    @property
    def _viewer(self):
        return self._host.dxf_viewer

    @property
    def _panel(self):
        return self._host.layout_panel

    def wire(self) -> None:
        panel = self._panel
        panel.sheetActivated.connect(self.activate)
        panel.addRequested.connect(self.add)
        panel.duplicateRequested.connect(lambda: self.duplicate(self._sheets.active_index))
        panel.renameRequested.connect(lambda: self.rename(self._sheets.active_index))
        panel.deleteRequested.connect(lambda: self.delete(self._sheets.active_index))
        panel.moveUpRequested.connect(lambda: self.move(-1))
        panel.moveDownRequested.connect(lambda: self.move(1))
        panel.exportAllRequested.connect(self.export_all)
        panel.optionsChanged.connect(self.on_options_changed)
        panel.exportRequested.connect(self.export_active)
        panel.centerRequested.connect(self.center_on_drawing)

        tabs = self._viewer.sheet_tabs
        tabs.modelActivated.connect(lambda: self.activate(None))
        tabs.sheetActivated.connect(self.activate)
        tabs.addRequested.connect(self.add)
        tabs.renameRequested.connect(self.rename)
        tabs.duplicateRequested.connect(self.duplicate)
        tabs.deleteRequested.connect(self.delete)

        self._viewer.pageFrameMoved.connect(self.on_page_frame_moved)
        self._viewer.pageFrameRotated.connect(self.on_page_frame_rotated)
        panel.projectFieldsChanged.connect(self.on_project_fields_changed)

    def reapply(self) -> None:
        self._apply_active()
        self.refresh()

    def refresh(self) -> None:
        names = self._sheets.names()
        active = self._sheets.active_index
        signature = (tuple(names), active)
        if signature != self._tab_signature:
            self._tab_signature = signature
            self._viewer.sheet_tabs.refresh(names, active)
        self._panel.refresh(names, active, self._viewer.has_document)
        self._sync_plot_tab()
        self._panel.set_coverage_text(self._coverage_text())

    def _sync_plot_tab(self) -> None:
        sheet = self._sheets.active
        if sheet is None:
            return
        self._syncing = True
        try:
            self._panel.plot_tab.set_options(sheet.options)
            self._panel.plot_tab.set_rotation(sheet.rotation)
            self._panel.sheet_fields_tab.set_values(sheet.field_values)
        finally:
            self._syncing = False

    def activate(self, index: Optional[int]) -> None:
        self._sheets.activate(index)
        self._apply_active()
        self.refresh()

    def _apply_active(self) -> None:
        sheet = self._sheets.active
        if sheet is None:
            self._viewer.set_layout_mode(None)
            return
        options = self._resolved(sheet)
        self._viewer.set_layout_mode(
            options, self._center(sheet), self._label(sheet, options), sheet.rotation,
            table_height_mm=self._host.table_template.total_height_mm(),
            table_width_mm=MAX_TABLE_WIDTH_MM,
        )
        self._apply_table(sheet, options)

    def _apply_table(self, sheet: Sheet, options: PlotOptions) -> None:
        template = self._host.table_template
        frame = page_frame_for(
            options, self._center(sheet), rotation=sheet.rotation,
            table_height_mm=template.total_height_mm(), table_width_mm=MAX_TABLE_WIDTH_MM,
        )
        table = frame.table_rect()
        scale = units_per_mm(options)
        local_table = Rect(0.0, 0.0, table.width(), table.height())
        cells = table_layout(template, local_table, sheet.field_values, template.project_field_values, scale=scale)
        self._viewer.set_title_block(cells, scale)

    @staticmethod
    def _label(sheet: Sheet, options: PlotOptions) -> str:
        return f"{sheet.name} · {sheet_label(options)}"

    def _content_size(self) -> Optional[Vec2]:
        box = self._viewer.content_bbox()
        return Vec2(box.size.x, box.size.y) if box is not None else None

    def _resolved(self, sheet: Sheet) -> PlotOptions:
        return resolved_options(sheet.options, self._content_size(), self._host.table_template.total_height_mm())

    def _center(self, sheet: Sheet) -> Tuple[float, float]:
        if sheet.center is not None:
            return sheet.center
        return self._viewer.content_center() or (0.0, 0.0)

    def frame_for(self, sheet: Sheet) -> PageFrame:
        options = self._resolved(sheet)
        return page_frame_for(
            options, self._center(sheet), self._label(sheet, options), sheet.rotation,
            table_height_mm=self._host.table_template.total_height_mm(),
            table_width_mm=MAX_TABLE_WIDTH_MM,
        )

    def on_options_changed(self) -> None:
        if self._syncing:
            return
        index = self._sheets.active_index
        if index is None:
            return
        self._sheets.set_options(index, self._panel.plot_tab.get_options())
        self._sheets.set_rotation(index, self._panel.plot_tab.get_rotation())
        self._sheets.set_field_values(index, self._panel.sheet_fields_tab.get_values())
        self._apply_active()
        self.refresh()

    def on_project_fields_changed(self) -> None:
        if self._syncing:
            return
        values = self._panel.project_fields_tab.get_values()
        self._host.table_template = replace(self._host.table_template, project_field_values=values)
        self._apply_active()

    def on_page_frame_moved(self, center_x: float, center_y: float) -> None:
        index = self._sheets.active_index
        if index is None:
            return
        self._sheets.set_center(index, (center_x, center_y))
        self._panel.set_coverage_text(self._coverage_text())

    def on_page_frame_rotated(self, rotation: float) -> None:
        index = self._sheets.active_index
        if index is None:
            return
        self._sheets.set_rotation(index, rotation)
        self._sync_plot_tab()
        self._panel.set_coverage_text(self._coverage_text())

    def center_on_drawing(self) -> None:
        index = self._sheets.active_index
        if index is None:
            return
        self._sheets.set_center(index, None)
        self._apply_active()
        self.refresh()

    def add(self) -> None:
        template = self._sheets.active
        self._sheets.add(template.options if template is not None else None)
        self._apply_active()
        self.refresh()

    def duplicate(self, index: Optional[int]) -> None:
        if index is None:
            return
        self._sheets.duplicate(index)
        self._apply_active()
        self.refresh()

    def rename(self, index: Optional[int]) -> None:
        if index is None:
            return
        current = self._sheets.at(index).name
        name, accepted = QInputDialog.getText(
            self._host, "Rename sheet", "Sheet name:", text=current
        )
        if not accepted:
            return
        applied = self._sheets.rename(index, name)
        if self._sheets.active_index == index:
            self._apply_active()
        self.refresh()
        if name.strip() and applied != name.strip():
            self._host.flash_status(f'"{name.strip()}" was taken, so this sheet is "{applied}".')

    def delete(self, index: Optional[int]) -> None:
        if index is None:
            return
        name = self._sheets.at(index).name
        confirmed = QMessageBox.question(
            self._host,
            "Delete sheet",
            f'Delete "{name}"? Its page settings are lost. The drawing itself is not affected.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._sheets.delete(index)
        self._apply_active()
        self.refresh()

    def move(self, delta: int) -> None:
        index = self._sheets.active_index
        if index is None:
            return
        self._sheets.move(index, index + delta)
        self.refresh()

    def job_for(self, index: int) -> PlotJob:
        sheet = self._sheets.at(index)
        options = self._resolved(sheet)
        return PlotJob(sheet.name, options, self.frame_for(sheet), self._host.table_template, sheet.field_values)

    def export_active(self) -> None:
        index = self._sheets.active_index
        if index is None:
            return
        self._export([self.job_for(index)], self._sheets.at(index).name)

    def export_all(self) -> None:
        count = len(self._sheets)
        if count == 0:
            return
        self._export([self.job_for(index) for index in range(count)], self._host.project.name)

    def _export(self, jobs: List[PlotJob], suggested: str) -> None:
        if not self._viewer.has_document:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._host, "Export PDF", f"{suggested}.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        ok, message = self._viewer.export_sheets(path, jobs, title=self._host.project.name)
        if not ok:
            self._host.flash_status(message, ms=5000)
            return
        sheets = "sheet" if len(jobs) == 1 else "sheets"
        self._host.flash_status(f"Exported {len(jobs)} {sheets} to {os.path.basename(path)}")

    def _coverage_text(self) -> str:
        sheet = self._sheets.active
        if sheet is None:
            return ""
        options = self._resolved(sheet)
        box = self._viewer.content_bbox()
        if box is None:
            return "The drawing is empty — there is nothing to plot yet."
        frame = self.frame_for(sheet)
        printable = frame.map_rect()
        pivot = (frame.center_x, frame.center_y)
        xmin, ymin, xmax, ymax = rotated_bbox_extents(
            box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y, pivot, frame.rotation
        )
        content = QRectF(xmin, ymin, xmax - xmin, ymax - ymin)
        if printable.contains(content):
            return f"The whole drawing fits on this sheet at {scale_label(options)}."
        area = content.width() * content.height()
        if area <= 0.0:
            return f"Plotting at {scale_label(options)}."
        covered = printable.intersected(content)
        ratio = covered.width() * covered.height() / area
        return (
            f"About {ratio:.0%} of the drawing fits at {scale_label(options)} — "
            "pan with the middle mouse button to move it."
        )
