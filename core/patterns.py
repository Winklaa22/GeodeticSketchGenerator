"""Detects two shapes among consecutively-numbered survey points, for the
LINES/PLINES/POLY3D drawing modes:

  * "skrzynka" (junction box) — 4 consecutive points that trace a rectangle
    (checked directly: every corner's interior angle is ~90°, in the points'
    existing numeric order — survey numbering already walks a box's corners
    in perimeter order). The box is entirely separate from the cable run: the
    cable skips over all 4 corners and connects straight from the point
    before the box to whatever point comes next, if any — it never touches
    any of the box's vertices.

  * "wcinka" (splice/joint) — 3 consecutive points, right at the very start
    or end of the selection, that sit unusually close together compared to
    the rest of the run (a real splice is a small huddle of points next to a
    much longer cable, not just another ordinary segment of it). Unlike a
    box, a wcinka *does* connect to the cable: whichever of the 3 is nearest
    to the run's other end becomes the entry point and stays part of the
    main path; the other two are drawn as two open "wing" stubs off of it —
    a triangle with its far side left undrawn, since nothing connects those
    two points to each other. Detection is restricted to the two ends of the
    selection (not the middle) so an ordinary bend or wiggle partway along a
    cable run — ordinary points that just happen to sit close together —
    never gets mistaken for a splice.

Anything that matches neither shape is left exactly as before: a straight
chain in numeric order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.point import Point

# How far an interior angle may deviate from 90° and still count as a right
# angle, for the "is this a rectangle" check.
RIGHT_ANGLE_TOLERANCE_DEG = 15.0

# A run of 3 points only counts as a wcinka if its internal edges are this
# fraction (or less) of the selection's longest segment — i.e. it has to
# look like a small huddle of points next to a much longer cable run.
WCINKA_SIZE_RATIO = 0.35

_RECTANGLE_SIZE = 4
_WCINKA_SIZE = 3


@dataclass(frozen=True)
class RoutedPath:
    """The result of `route_selected_points`.

    `main` is the vertex path for the cable run itself (LINE chain / single
    PLINE / POLY3D) — it skips over each detected box entirely, but does
    pass through each detected wcinka's entry point. `boxes` holds each
    detected rectangle's 4 corners, in perimeter order, for drawing as its
    own separate closed shape that shares no vertex with the cable.
    `wedges` holds each detected wcinka as (entry, wing_1, wing_2) — draw
    entry-wing_1 and entry-wing_2 as two separate open stubs; there is no
    wing_1-wing_2 edge, that's the triangle's deliberately missing side.
    """

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
    # Prefer connecting onward (the wcinka is at the start of the selection,
    # or mid-walk with more cable ahead); fall back to connecting back to
    # where we came from if there's nothing ahead; and if the 3 points are
    # the entire selection, there's no real neighbour to anchor on at all.
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
