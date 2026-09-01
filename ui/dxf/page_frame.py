from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

from PyQt6 import QtCore as qc

from core.plot import PlotOptions, margin_in_units, normalize_degrees, sheet_size_in_units


@dataclass(frozen=True)
class PageFrame:
    center_x: float
    center_y: float
    width: float
    height: float
    margin: float
    label: str = ""
    rotation: float = 0.0

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

    def moved_to(self, center_x: float, center_y: float) -> "PageFrame":
        return replace(self, center_x=center_x, center_y=center_y)

    def rotated_to(self, rotation: float) -> "PageFrame":
        return replace(self, rotation=normalize_degrees(rotation))


def page_frame_for(
    options: PlotOptions, center: Tuple[float, float], label: str = "", rotation: float = 0.0
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
    )
