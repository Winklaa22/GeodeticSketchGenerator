from __future__ import annotations

from typing import Dict, List, Tuple

from core.config import GenerationConfig
from core.draw_modes import ScriptDrawer
from core.geometry import AngleQuadrant, classify_quadrant, iter_point_directions, snap_small_rotation
from models.point import Point


class CableDrawer(ScriptDrawer):

    def generate(self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig) -> List[str]:
        options = config.cable
        lines: List[str] = []
        for direction in iter_point_directions(points, selected_numbers):
            if direction.next_point is None:
                continue
            if direction.number % options.frequency != 0:
                continue
            mid_x = (direction.point.x + direction.next_point.x) / 2.0
            mid_y = (direction.point.y + direction.next_point.y) / 2.0
            x_offset, y_offset = self._label_offset(direction.angle_deg, options.font_size)
            rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
            lines.append(
                f"-TEXT {mid_x + x_offset},{mid_y + y_offset},{direction.point.h} "
                f"{options.font_size} {rotation} {options.marks_text}"
            )
        return lines

    @staticmethod
    def _label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
        half = font_size / 2.0
        offsets = {
            AngleQuadrant.NORTH_EAST: (half, 0.0),
            AngleQuadrant.NORTH_WEST: (0.0, half),
            AngleQuadrant.SOUTH_WEST: (-half, 0.0),
            AngleQuadrant.SOUTH_EAST: (0.0, -half),
        }
        return offsets[classify_quadrant(angle_deg)]
