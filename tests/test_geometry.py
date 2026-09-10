from __future__ import annotations

import math

from core.geometry import (
    compute_direction_angle,
    get_next_point,
    offset_segment_perpendicular,
    snap_small_rotation,
)
from models.point import Point


def test_compute_direction_angle_returns_zero_without_next_point() -> None:
    assert compute_direction_angle(Point(0, 0, 0), None) == 0.0


def test_compute_direction_angle_returns_zero_for_coincident_points() -> None:
    assert compute_direction_angle(Point(1, 1, 0), Point(1, 1, 0)) == 0.0


def test_compute_direction_angle_flips_leftward_angles() -> None:
    angle = compute_direction_angle(Point(0, 0, 0), Point(-1, 0, 0))
    assert angle == 0.0


def test_snap_small_rotation_zeroes_near_flat_angles() -> None:
    assert snap_small_rotation(10.0, 10.0) == 0.0
    assert snap_small_rotation(45.0, 45.0) == 45.0


def test_get_next_point_returns_none_for_last_selected() -> None:
    points = {1: Point(0, 0, 0), 2: Point(1, 0, 0)}
    assert get_next_point(points, 2, last_selected=2) is None
    assert get_next_point(points, 1, last_selected=2) == points[2]


def test_offset_segment_perpendicular_shifts_a_horizontal_segment_vertically() -> None:
    start, end = offset_segment_perpendicular(Point(0, 0, 5), Point(10, 0, 6), offset=1.0)
    assert (start.x, start.y, start.h) == (0.0, 1.0, 5.0)
    assert (end.x, end.y, end.h) == (10.0, 1.0, 6.0)


def test_offset_segment_perpendicular_flips_side_for_negative_offset() -> None:
    start, end = offset_segment_perpendicular(Point(0, 0, 0), Point(10, 0, 0), offset=-1.0)
    assert (start.y, end.y) == (-1.0, -1.0)


def test_offset_segment_perpendicular_stays_perpendicular_for_a_diagonal_segment() -> None:
    start, end = offset_segment_perpendicular(Point(0, 0, 0), Point(3, 4, 0), offset=5.0)
    shift = (end.x - 3, end.y - 4)
    assert math.isclose(shift[0] * 3 + shift[1] * 4, 0.0, abs_tol=1e-9)
    assert math.isclose(math.hypot(*shift), 5.0)


def test_offset_segment_perpendicular_leaves_a_zero_length_segment_unshifted() -> None:
    start, end = offset_segment_perpendicular(Point(1, 1, 0), Point(1, 1, 0), offset=2.0)
    assert (start.x, start.y) == (1.0, 1.0)
    assert (end.x, end.y) == (1.0, 1.0)
