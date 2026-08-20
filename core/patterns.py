"""Detects two shapes among consecutively-numbered survey points, for the
LINES/PLINES/POLY3D drawing modes.

"Skrzynka" (junction box): 4 consecutive points whose corners are all near
90°. Drawn as its own closed rectangle; the cable skips over it entirely.

"Wcinka" (splice): 3 consecutive points at either end of the selection,
much closer together than the rest of the run. Drawn as an open triangle —
two stubs off an entry point, far side left undrawn — with the entry point
staying on the cable's path.

Anything else is left as a straight chain in numeric order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.point import Point

RIGHT_ANGLE_TOLERANCE_DEG = 15.0  # max deviation from 90° for a rectangle corner
WCINKA_SIZE_RATIO = 0.35  # a 3-point run only counts as a wcinka if its edges are this small a fraction of the longest segment

_RECTANGLE_SIZE = 4
_WCINKA_SIZE = 3


@dataclass(frozen=True)
class RoutedPath:
    """`main`: the cable's own vertex path — skips each box, passes through
    each wcinka's entry point. `boxes`: each rectangle's 4 corners.
    `wedges`: each wcinka as (entry, wing_1, wing_2) — draw entry-wing_1 and
    entry-wing_2 only; there's no wing_1-wing_2 edge."""

    main: List[Point]
    boxes: List[List[Point]] = field(default_factory=list)
    wedges: List[Tuple[Point, Point, Point]] = field(default_factory=list)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _ordered_points(points: Dict[int, Point], selected_numbers: List[int]) -> List[Point]:
    return [points[n] for n in selected_numbers if n in points]


def _longest_segment(ordered: List[Point]) -> float:
    lengths = [length for a, b in zip(ordered, ordered[1:]) if (length := _distance(a, b)) > 0]
    return max(lengths) if lengths else 0.0


def _corner_angle_deg(prev_point: Point, corner: Point, next_point: Point) -> float:
    v1 = (prev_point.x - corner.x, prev_point.y - corner.y)
    v2 = (next_point.x - corner.x, next_point.y - corner.y)
    len1 = math.hypot(*v1)
    len2 = math.hypot(*v2)
    if len1 <= 0 or len2 <= 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)))
    return math.degrees(math.acos(cos_angle))


def _is_rectangle(window: List[Point]) -> bool:
    """True if the 4 points, taken in their given order, trace a rectangle —
    i.e. every corner's interior angle is a right angle."""
    for k in range(_RECTANGLE_SIZE):
        prev_point = window[k - 1]
        corner = window[k]
        next_point = window[(k + 1) % _RECTANGLE_SIZE]
        angle = _corner_angle_deg(prev_point, corner, next_point)
        if abs(angle - 90.0) > RIGHT_ANGLE_TOLERANCE_DEG:
            return False
    return True


def _is_tight_triangle(window: List[Point], threshold: float) -> bool:
    if threshold <= 0:
        return False
    pairs = ((0, 1), (1, 2), (0, 2))
    return all(0 < _distance(window[a], window[b]) <= threshold for a, b in pairs)


def _pick_wcinka_entry(window: List[Point], prev_point: Optional[Point], next_point: Optional[Point]) -> Point:
    # Prefer connecting onward; fall back to the previous point if there's
    # nothing ahead; no anchor at all if the wcinka is the whole selection.
    anchor = next_point if next_point is not None else prev_point
    if anchor is None:
        return window[0]
    return min(window, key=lambda p: _distance(anchor, p))


def route_selected_points(points: Dict[int, Point], selected_numbers: List[int]) -> RoutedPath:
    """Splits the selection into the cable run's own vertex path and any
    skrzynka/wcinka shapes found along the way (see module docstring).
    `main` alone is identical to the plain numeric-order point list when
    neither shape is found."""
    ordered = _ordered_points(points, selected_numbers)
    if len(ordered) < 2:
        return RoutedPath(main=ordered)

    wcinka_threshold = _longest_segment(ordered) * WCINKA_SIZE_RATIO
    main: List[Point] = []
    boxes: List[List[Point]] = []
    wedges: List[Tuple[Point, Point, Point]] = []
    index = 0
    total = len(ordered)
    while index < total:
        remaining = total - index

        if remaining >= _RECTANGLE_SIZE and _is_rectangle(ordered[index : index + _RECTANGLE_SIZE]):
            boxes.append(ordered[index : index + _RECTANGLE_SIZE])
            index += _RECTANGLE_SIZE
            continue

        at_an_end = index == 0 or index + _WCINKA_SIZE == total
        if at_an_end and remaining >= _WCINKA_SIZE:
            window = ordered[index : index + _WCINKA_SIZE]
            if _is_tight_triangle(window, wcinka_threshold):
                prev_point = main[-1] if main else None
                next_point = ordered[index + _WCINKA_SIZE] if index + _WCINKA_SIZE < total else None
                entry = _pick_wcinka_entry(window, prev_point, next_point)
                wing_1, wing_2 = (p for p in window if p is not entry)
                main.append(entry)
                wedges.append((entry, wing_1, wing_2))
                index += _WCINKA_SIZE
                continue

        main.append(ordered[index])
        index += 1

    return RoutedPath(main=main, boxes=boxes, wedges=wedges)
