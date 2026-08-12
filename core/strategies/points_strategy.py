"""Points drawing-mode strategy: a circle per point, with optional number labels."""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from core.config import GenerationConfig
from core.draw_modes import ScriptDrawer
from core.geometry import AngleQuadrant, PointDirection, classify_quadrant, iter_point_directions
from models.point import Point

CABINET_LABEL_COUNT = 6


class PointsDrawer(ScriptDrawer):
    """Draws a CIRCLE at each selected point, with an optional -TEXT number
    label offset away from the point's direction of travel so the label
    doesn't overlap the line. In "cabinet mode", the last 6 selected labels
    are drawn smaller and without an offset.
    """

    def generate(self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig) -> List[str]:
        options = config.points
        radius = max(options.diameter / 2.0, 0.0)
        cabinet_targets = self._cabinet_targets(selected_numbers, config.cabinet_mode)

        lines: List[str] = []
        for direction in iter_point_directions(points, selected_numbers):
            point = direction.point
            lines.append(f"CIRCLE {point.x},{point.y},{point.h} {radius}")
            if options.numbers_enabled:
                lines.append(self._build_label_line(direction, options.font_size, config.cabinet_mode, cabinet_targets))
        return lines

    @staticmethod
    def _cabinet_targets(selected_numbers: List[int], cabinet_mode: bool) -> Set[int]:
        if not cabinet_mode:
            return set()
        return set(sorted(selected_numbers)[-CABINET_LABEL_COUNT:])

    @staticmethod
    def _build_label_line(
        direction: PointDirection, font_size: float, cabinet_mode: bool, cabinet_targets: Set[int]
    ) -> str:
        point = direction.point
        x_offset, y_offset = PointsDrawer._label_offset(direction.angle_deg, font_size)
        size = font_size
        if cabinet_mode and direction.number in cabinet_targets:
            size = font_size / 2.0
            x_offset = 0.0
            y_offset = 0.0
        return f"-TEXT {point.x + x_offset},{point.y + y_offset},{point.h} {size} 0 {direction.number}"

    @staticmethod
    def _label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
        half = font_size / 2.0
        offsets = {
            AngleQuadrant.NORTH_EAST: (half, -half),
            AngleQuadrant.NORTH_WEST: (-half, half),
            AngleQuadrant.SOUTH_WEST: (-half, -half),
            AngleQuadrant.SOUTH_EAST: (-half, half),
        }
        return offsets[classify_quadrant(angle_deg)]
