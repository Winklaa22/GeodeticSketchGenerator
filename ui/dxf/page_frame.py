from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

from PyQt6 import QtCore as qc

from core.plot import PlotOptions, margin_in_units, normalize_degrees, sheet_size_in_units, units_per_mm


@dataclass(frozen=True)
class PageFrame:
    center_x: float
    center_y: float
    width: float
    height: float
    margin: float
    label: str = ""
    rotation: float = 0.0
    table_height: float = 0.0
    table_width: float = 0.0

    def sheet_rect(self) -> qc.QRectF:
        return qc.QRectF(
            self.center_x - self.width / 2.0,
            self.center_y - self.height / 2.0,
            self.width,
            self.height,
        )

    def printable_rect(self) -> qc.QRectF:
        rect = self.sheet_rect()
        inset = min(self.margin, rect.width() / 2.0, rect.height() / 2.0)
        return rect.adjusted(inset, inset, -inset, -inset)

    def map_rect(self) -> qc.QRectF:
        printable = self.printable_rect()
        # Scene space is Y-up: printable.top() (the smaller y) is the visual BOTTOM of
        # the page, so the table is carved off starting there, and the map fills the rest.
        top_edge = min(printable.top() + self.table_height, printable.bottom())
        return qc.QRectF(printable.left(), top_edge, printable.width(), printable.bottom() - top_edge)

    def table_rect(self) -> qc.QRectF:
        printable = self.printable_rect()
        map_rect = self.map_rect()
        # table_width <= 0 means "no cap" - keeps callers that never asked for one (tests,
        # anything not sizing an actual table) at the old full-printable-width behaviour.
        width = printable.width() if self.table_width <= 0.0 else min(printable.width(), self.table_width)
        return qc.QRectF(printable.left(), printable.top(), width, map_rect.top() - printable.top())

    def moved_to(self, center_x: float, center_y: float) -> "PageFrame":
        return replace(self, center_x=center_x, center_y=center_y)

    def rotated_to(self, rotation: float) -> "PageFrame":
        return replace(self, rotation=normalize_degrees(rotation))


def page_frame_for(
    options: PlotOptions,
    center: Tuple[float, float],
    label: str = "",
    rotation: float = 0.0,
    table_height_mm: float = 0.0,
    table_width_mm: float = 0.0,
) -> PageFrame:
    width, height = sheet_size_in_units(options)
    return PageFrame(
        center_x=center[0],
        center_y=center[1],
        width=width,
        height=height,
        margin=margin_in_units(options),
        label=label,
        rotation=normalize_degrees(rotation),
        table_height=table_height_mm * units_per_mm(options),
        table_width=table_width_mm * units_per_mm(options),
    )
