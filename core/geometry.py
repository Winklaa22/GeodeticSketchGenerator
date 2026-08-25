from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Iterator, List, Optional, Tuple, Union

from models.point import Point


def compute_direction_angle(current: Point, next_point: Optional[Point]) -> float:

    if next_point is None:
        return 0.0
    dx = next_point.x - current.x
    dy = next_point.y - current.y
    if dx == 0 and dy == 0:
        return 0.0
    angle_deg = math.degrees(math.atan2(dy, dx))
    if angle_deg < 0:
        angle_deg += 360
    if 90 < angle_deg < 270:
        angle_deg += 180
        if angle_deg >= 360:
            angle_deg -= 360
    return angle_deg


class AngleQuadrant(IntEnum):

    NORTH_EAST = 0
    NORTH_WEST = 1
    SOUTH_WEST = 2
    SOUTH_EAST = 3


def classify_quadrant(angle_deg: float) -> AngleQuadrant:
    if 45 <= angle_deg < 135:
        return AngleQuadrant.NORTH_EAST
    if 135 <= angle_deg < 225:
        return AngleQuadrant.NORTH_WEST
    if 225 <= angle_deg < 315:
        return AngleQuadrant.SOUTH_WEST
    return AngleQuadrant.SOUTH_EAST


def snap_small_rotation(angle_deg: float, rotation: float, threshold: float = 20.0) -> Union[int, float]:

    return 0 if 0 <= angle_deg < threshold else rotation


def get_next_point(points: Dict[int, Point], number: int, last_selected: int) -> Optional[Point]:

    if number < last_selected and (number + 1) in points:
        return points[number + 1]
    return None


def offset_segment_perpendicular(start: Point, end: Point, offset: float) -> Tuple[Point, Point]:
    dx, dy = end.x - start.x, end.y - start.y
    length = math.hypot(dx, dy)
    if length <= 0:
        return start, end
    ux, uy = -dy / length, dx / length
    shift_x, shift_y = ux * offset, uy * offset
    return (
        Point(start.x + shift_x, start.y + shift_y, start.h),
        Point(end.x + shift_x, end.y + shift_y, end.h),
    )


@dataclass(frozen=True)
class PointDirection:

    number: int
    point: Point
    next_point: Optional[Point]
    angle_deg: float
    rotation: float


def iter_point_directions(points: Dict[int, Point], selected_numbers: List[int]) -> Iterator[PointDirection]:

    last_selected = max(selected_numbers) if selected_numbers else 0
    for number in selected_numbers:
        point = points.get(number)
        if point is None:
            continue
        next_point = get_next_point(points, number, last_selected)
        angle_deg = compute_direction_angle(point, next_point)
        yield PointDirection(
            number=number,
            point=point,
            next_point=next_point,
            angle_deg=angle_deg,
            rotation=round(angle_deg, 1),
        )
