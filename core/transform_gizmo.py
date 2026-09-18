from __future__ import annotations

import math
from typing import Optional, Tuple

Point = Tuple[float, float]
Box = Tuple[Point, Point]

MIN_RADIUS = 1e-9


def center_of(minimum: Point, maximum: Point) -> Point:
    return (minimum[0] + maximum[0]) / 2.0, (minimum[1] + maximum[1]) / 2.0


def bbox_corners(minimum: Point, maximum: Point) -> Tuple[Point, ...]:
    """The four grips, counter-clockwise from the bottom-left corner."""
    return (
        (minimum[0], minimum[1]),
        (maximum[0], minimum[1]),
        (maximum[0], maximum[1]),
        (minimum[0], maximum[1]),
    )


def knob_point(minimum: Point, maximum: Point, offset: float) -> Point:
    """Where the rotation grip sits: above the middle of the box's top edge."""
    return (minimum[0] + maximum[0]) / 2.0, maximum[1] + offset


def scale_factor(center: Point, grabbed: Point, cursor: Point) -> Optional[float]:
    """How much to scale so the grabbed grip lands under the cursor.

    A ratio of two distances from the centre, so the same drag means the same thing at
    any zoom and on any sheet scale. ``None`` when the grip sits on the centre, where no
    ratio is defined.
    """
    radius = math.hypot(grabbed[0] - center[0], grabbed[1] - center[1])
    if radius <= MIN_RADIUS:
        return None
    factor = math.hypot(cursor[0] - center[0], cursor[1] - center[1]) / radius
    return factor if factor > 0.0 else None


def rotation_delta(center: Point, grabbed: Point, cursor: Point) -> float:
    """Degrees swept from the grabbed grip to the cursor, about the centre.

    Wrapped to (-180, 180]: the two atan2 readings can sit two turns apart, and reporting
    a quarter turn as -268 degrees would be the same rotation spelled the long way round.
    """
    start = math.atan2(grabbed[1] - center[1], grabbed[0] - center[0])
    now = math.atan2(cursor[1] - center[1], cursor[0] - center[0])
    return math.degrees(math.atan2(math.sin(now - start), math.cos(now - start)))
