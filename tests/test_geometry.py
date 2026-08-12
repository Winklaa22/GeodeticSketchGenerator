"""Tests for core.geometry direction/angle helpers."""
from __future__ import annotations

from core.geometry import (
    AngleQuadrant,
    classify_quadrant,
    compute_direction_angle,
    get_next_point,
    snap_small_rotation,
)
from models.point import Point


def test_compute_direction_angle_returns_zero_without_next_point() -> None:
    assert compute_direction_angle(Point(0, 0, 0), None) == 0.0


def test_compute_direction_angle_returns_zero_for_coincident_points() -> None:
    assert compute_direction_angle(Point(1, 1, 0), Point(1, 1, 0)) == 0.0


def test_compute_direction_angle_flips_leftward_angles() -> None:
    # Straight left (180 degrees) should flip to 0.
    angle = compute_direction_angle(Point(0, 0, 0), Point(-1, 0, 0))
    assert angle == 0.0


def test_classify_quadrant_bands() -> None:
    assert classify_quadrant(90) == AngleQuadrant.NORTH_EAST
    assert classify_quadrant(180) == AngleQuadrant.NORTH_WEST
    assert classify_quadrant(270) == AngleQuadrant.SOUTH_WEST
    assert classify_quadrant(0) == AngleQuadrant.SOUTH_EAST


def test_snap_small_rotation_zeroes_near_flat_angles() -> None:
    assert snap_small_rotation(10.0, 10.0) == 0.0
    assert snap_small_rotation(45.0, 45.0) == 45.0


def test_get_next_point_returns_none_for_last_selected() -> None:
    points = {1: Point(0, 0, 0), 2: Point(1, 0, 0)}
    assert get_next_point(points, 2, last_selected=2) is None
    assert get_next_point(points, 1, last_selected=2) == points[2]
