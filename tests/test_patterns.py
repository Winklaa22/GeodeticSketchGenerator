"""Tests for core.patterns: skrzynka (junction box) and wcinka (splice)
shape detection and routing for the LINES/PLINES/POLY3D drawing modes."""
from __future__ import annotations

from core.patterns import route_selected_points
from models.point import Point


def test_plain_run_is_unaffected() -> None:
    points = {i: Point(x=float(i) * 10.0, y=0.0, h=0.0) for i in range(1, 6)}
    routed = route_selected_points(points, [1, 2, 3, 4, 5])
    assert routed.main == [points[1], points[2], points[3], points[4], points[5]]
    assert routed.boxes == []
    assert routed.wedges == []


def test_short_selection_is_returned_unchanged() -> None:
    points = {1: Point(0, 0, 0), 2: Point(1, 0, 0)}
    routed = route_selected_points(points, [1, 2])
    assert routed.main == [points[1], points[2]]
    assert routed.boxes == []
    assert routed.wedges == []


def test_rectangle_is_split_out_and_main_run_skips_it_entirely() -> None:
    # Point 1 is a normal main-line point; 2,3,4,5 trace a rectangle (in
    # perimeter order); point 6 continues the main line afterwards.
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(11.0, 0.0, 0.0),
        4: Point(11.0, 1.0, 0.0),
        5: Point(10.0, 1.0, 0.0),
        6: Point(20.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4, 5, 6])
    # The cable run skips the box entirely - it connects straight from 1 to
    # 6 and never touches any of the box's 4 corners.
    assert routed.main == [points[1], points[6]]
    # The box itself is reported separately, as its own closed shape.
    assert routed.boxes == [[points[2], points[3], points[4], points[5]]]


def test_rectangle_with_no_point_after_it() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(11.0, 0.0, 0.0),
        4: Point(11.0, 1.0, 0.0),
        5: Point(10.0, 1.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4, 5])
    assert routed.main == [points[1]]
    assert routed.boxes == [[points[2], points[3], points[4], points[5]]]


def test_non_rectangular_run_of_four_is_left_as_a_plain_chain() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(10.3, 0.1, 0.0),  # not a rectangle - just a slight wiggle
        4: Point(10.6, -0.1, 0.0),
        5: Point(10.9, 0.2, 0.0),
        6: Point(20.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4, 5, 6])
    assert routed.main == [points[1], points[2], points[3], points[4], points[5], points[6]]
    assert routed.boxes == []


def test_fewer_than_four_points_is_left_as_a_plain_chain_when_nothing_is_tight() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(20.0, 0.0, 0.0),
        4: Point(30.0, 0.0, 0.0),
    }
    # Only 4 points total - not enough for a rectangle, and evenly spaced
    # (not tight), so no wcinka either.
    routed = route_selected_points(points, [1, 2, 3, 4])
    assert routed.main == [points[1], points[2], points[3], points[4]]
    assert routed.boxes == []
    assert routed.wedges == []


def test_selection_with_unknown_numbers_is_ignored() -> None:
    points = {1: Point(0, 0, 0), 2: Point(1, 0, 0), 3: Point(2, 0, 0)}
    routed = route_selected_points(points, [1, 99, 2, 3])
    assert routed.main == [points[1], points[2], points[3]]
    assert routed.boxes == []


def test_two_consecutive_rectangles() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        # first box
        2: Point(10.0, 0.0, 0.0),
        3: Point(11.0, 0.0, 0.0),
        4: Point(11.0, 1.0, 0.0),
        5: Point(10.0, 1.0, 0.0),
        # second box, right after the first
        6: Point(20.0, 0.0, 0.0),
        7: Point(21.0, 0.0, 0.0),
        8: Point(21.0, 1.0, 0.0),
        9: Point(20.0, 1.0, 0.0),
        10: Point(30.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, list(range(1, 11)))
    assert routed.main == [points[1], points[10]]
    assert routed.boxes == [
        [points[2], points[3], points[4], points[5]],
        [points[6], points[7], points[8], points[9]],
    ]


def test_wcinka_at_the_start_connects_via_the_corner_nearest_the_next_point() -> None:
    # 1, 2, 3 are a tight little triangle right at the start of the
    # selection; 4 is a normal, far-away main-line point. Point 3 is the one
    # nearest to 4, so it's the entry point that stays on the cable's own
    # path; 1 and 2 become open stubs off of it - no 1-2 edge.
    points = {
        1: Point(2.0, -3.0, 0.0),
        2: Point(2.0, 3.0, 0.0),
        3: Point(0.0, 0.0, 0.0),
        4: Point(-20.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4])
    assert routed.main == [points[3], points[4]]
    assert routed.boxes == []
    assert routed.wedges == [(points[3], points[1], points[2])]


def test_wcinka_at_the_end_connects_via_the_corner_nearest_the_previous_point() -> None:
    # Mirror image of the above: the tight triangle is at the end of the
    # selection instead of the start.
    points = {
        1: Point(-20.0, 0.0, 0.0),
        2: Point(0.0, 0.0, 0.0),
        3: Point(2.0, -3.0, 0.0),
        4: Point(2.0, 3.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4])
    assert routed.main == [points[1], points[2]]
    assert routed.boxes == []
    assert routed.wedges == [(points[2], points[3], points[4])]


def test_wcinka_is_not_detected_in_the_middle_of_a_run() -> None:
    # The same tight triangle as above, but with a normal point on both
    # sides - a splice is a terminal feature, so a tight cluster mid-run
    # should be left as a plain chain instead of being mistaken for one.
    points = {
        1: Point(-20.0, 0.0, 0.0),
        2: Point(2.0, -3.0, 0.0),
        3: Point(0.0, 0.0, 0.0),
        4: Point(2.0, 3.0, 0.0),
        5: Point(20.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4, 5])
    assert routed.main == [points[1], points[2], points[3], points[4], points[5]]
    assert routed.boxes == []
    assert routed.wedges == []


def test_whole_selection_is_just_the_wcinka_with_no_real_neighbour() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(1.0, 0.0, 0.0),
        3: Point(0.5, 0.8, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3])
    # No real main-line segment to compare against, so nothing is "tight"
    # relative to anything - left as a plain chain.
    assert routed.main == [points[1], points[2], points[3]]
    assert routed.boxes == []
    assert routed.wedges == []
