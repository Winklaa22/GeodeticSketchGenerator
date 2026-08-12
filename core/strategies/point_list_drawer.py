"""Base strategy for drawing modes that simply emit one coordinate line per
selected point, optionally preceded by a single AutoCAD command.
"""
from __future__ import annotations

from typing import ClassVar, Dict, List, Optional

from core.config import GenerationConfig
from core.draw_modes import ScriptDrawer
from models.point import Point


class PointListDrawer(ScriptDrawer):
    """Emits an optional command line followed by one coordinate line per
    selected point. LINE, PLINE, and 3DPOLY are all instances of this shape -
    they only differ in the command and whether height is included.
    """

    command: ClassVar[Optional[str]] = None
    include_height: ClassVar[bool] = True

    def preamble(self) -> List[str]:
        return [self.command] if self.command else []

    def generate(self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig) -> List[str]:
        lines: List[str] = []
        for number in selected_numbers:
            point = points.get(number)
            if point is None:
                continue
            if self.include_height:
                lines.append(f"{point.x},{point.y},{point.h}")
            else:
                lines.append(f"{point.x},{point.y}")
        return lines
