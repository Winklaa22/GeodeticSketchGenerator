from __future__ import annotations

import math
from typing import Dict, List, Tuple

from core.config import GenerationConfig
from core.draw_modes import ScriptDrawer
from core.geometry import AngleQuadrant, classify_quadrant, iter_point_directions, snap_small_rotation
from models.point import Point


class HeightsDrawer(ScriptDrawer):

    def generate(self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig) -> List[str]:
        options = config.heights
        lines: List[str] = []
        for direction in iter_point_directions(points, selected_numbers):
            if direction.number % options.frequency != 0:
                continue
            point = direction.point
            x_offset, y_offset = self._label_offset(direction.angle_deg, options.font_size)
            rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
            rounded_height = math.ceil(point.h * 10) / 10
            lines.append(
                f"-TEXT {point.x + x_offset},{point.y + y_offset},{point.h} "
                f"{options.font_size} {rotation} {rounded_height}"
            )
        return lines

    @staticmethod
    def _label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
        half = font_size / 2.0
        offsets = {
            AngleQuadrant.NORTH_EAST: (half, 0.5),
            AngleQuadrant.NORTH_WEST: (-0.5, half),
            AngleQuadrant.SOUTH_WEST: (-half, -0.5),
            AngleQuadrant.SOUTH_EAST: (0.5, -half),
        }
        return offsets[classify_quadrant(angle_deg)]
