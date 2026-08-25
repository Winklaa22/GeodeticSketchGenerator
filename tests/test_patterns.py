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
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(11.0, 0.0, 0.0),
        4: Point(11.0, 1.0, 0.0),
        5: Point(10.0, 1.0, 0.0),
        6: Point(20.0, 0.0, 0.0),
    }
    routed = route_selected_points(points, [1, 2, 3, 4, 5, 6])
    assert routed.main == [points[1], points[6]]
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
        3: Point(10.3, 0.1, 0.0),
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
        2: Point(10.0, 0.0, 0.0),
        3: Point(11.0, 0.0, 0.0),
        4: Point(11.0, 1.0, 0.0),
        5: Point(10.0, 1.0, 0.0),
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
    assert routed.main == [points[1], points[2], points[3]]
    assert routed.boxes == []
    assert routed.wedges == []
