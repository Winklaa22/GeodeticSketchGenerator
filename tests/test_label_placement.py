from __future__ import annotations

import math

import pytest

from core.label_placement import LabelRequest, Obstacles, solve_label_positions


def _rect(cx: float, cy: float, font_size: float, text: str) -> tuple[float, float, float, float]:
    width = 0.62 * font_size * len(text) + 0.30 * font_size
    height = 1.30 * font_size
    return cx - width / 2.0, cy - height / 2.0, cx + width / 2.0, cy + height / 2.0


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def test_no_labels_returns_empty_results() -> None:
    positions, collisions = solve_label_positions([], Obstacles(markers=[], segments=[]), 0.1)
    assert positions == {}
    assert collisions == {}


def test_isolated_label_lands_on_the_innermost_ring_with_no_prefer() -> None:
    label = LabelRequest(key="a", anchor=(0.0, 0.0), text="1", font_size=1.0, prefer=None)
    obstacles = Obstacles(markers=[(0.0, 0.0, 0.05)], segments=[])
    positions, collisions = solve_label_positions([label], obstacles, 0.05)
    x, y = positions["a"]
    width = 0.62 * 1.0 * 1 + 0.30 * 1.0
    height = 1.30 * 1.0
    expected_radius = 0.05 + math.hypot(width, height) / 2.0
    assert math.hypot(x, y) == pytest.approx(expected_radius)
    assert collisions["a"] == 0


def test_explicit_prefer_pulls_the_label_toward_that_direction() -> None:
    label = LabelRequest(key="a", anchor=(0.0, 0.0), text="1", font_size=1.0, prefer=math.pi / 2.0)
    obstacles = Obstacles(markers=[], segments=[])
    positions, _collisions = solve_label_positions([label], obstacles, 0.05)
    x, y = positions["a"]
    assert y > abs(x)


def test_default_prefer_is_perpendicular_to_an_incident_segment() -> None:
    label = LabelRequest(key="a", anchor=(0.0, 0.0), text="1", font_size=0.6, prefer=None)
    segments = [((0.0, 0.0), (10.0, 0.0))]
    obstacles = Obstacles(markers=[], segments=segments)
    positions, _collisions = solve_label_positions([label], obstacles, 0.03)
    x, y = positions["a"]
    assert abs(y) > abs(x)


def test_default_prefer_is_radially_outward_for_a_tight_group() -> None:
    labels = [
        LabelRequest(key=1, anchor=(0.0, 1.0), text="1", font_size=1.0, prefer=None),
        LabelRequest(key=2, anchor=(1.0, 1.0), text="2", font_size=1.0, prefer=None),
        LabelRequest(key=3, anchor=(1.0, 0.0), text="3", font_size=1.0, prefer=None),
        LabelRequest(key=4, anchor=(0.0, 0.0), text="4", font_size=1.0, prefer=None),
    ]
    obstacles = Obstacles(markers=[(l.anchor[0], l.anchor[1], 0.05) for l in labels], segments=[])
    positions, _collisions = solve_label_positions(labels, obstacles, 0.05)
    assert positions[1][0] < 0.0 and positions[1][1] > 1.0
    assert positions[2][0] > 1.0 and positions[2][1] > 1.0
    assert positions[3][0] > 1.0 and positions[3][1] < 0.0
    assert positions[4][0] < 0.0 and positions[4][1] < 0.0


def test_two_labels_never_cross_each_others_voronoi_boundary() -> None:
    labels = [
        LabelRequest(key="left", anchor=(-1.0, 0.0), text="1", font_size=0.6, prefer=None),
        LabelRequest(key="right", anchor=(1.0, 0.0), text="2", font_size=0.6, prefer=None),
    ]
    obstacles = Obstacles(markers=[], segments=[])
    positions, collisions = solve_label_positions(labels, obstacles, 0.03)
    assert positions["left"][0] < 0.0
    assert positions["right"][0] > 0.0
    assert collisions["left"] == 0
    assert collisions["right"] == 0


def test_rectangle_never_overlaps_a_marker_it_does_not_belong_to() -> None:
    label = LabelRequest(key="a", anchor=(0.0, 0.0), text="1", font_size=0.6, prefer=None)
    obstacles = Obstacles(markers=[(0.0, 0.0, 0.03), (0.5, 0.0, 0.4)], segments=[])
    positions, collisions = solve_label_positions([label], obstacles, 0.03)
    rect = _rect(*positions["a"], 0.6, "1")
    nx = min(max(0.5, rect[0]), rect[2])
    ny = min(max(0.0, rect[1]), rect[3])
    assert math.hypot(0.5 - nx, 0.0 - ny) >= 0.4
    assert collisions["a"] == 0


def test_rectangle_avoids_a_crossing_segment_when_a_clean_side_exists() -> None:
    label = LabelRequest(key="a", anchor=(0.0, 5.0), text="1", font_size=0.6, prefer=None)
    obstacles = Obstacles(markers=[], segments=[((-20.0, 0.0), (20.0, 0.0))])
    positions, collisions = solve_label_positions([label], obstacles, 0.03)
    rect = _rect(*positions["a"], 0.6, "1")
    assert rect[1] > 0.0
    assert collisions["a"] == 0


def test_width_scales_with_character_count() -> None:
    labels = [
        LabelRequest(key="one", anchor=(0.0, 0.0), text="1", font_size=0.6, prefer=0.0),
        LabelRequest(key="two", anchor=(100.0, 0.0), text="22", font_size=0.6, prefer=0.0),
        LabelRequest(key="three", anchor=(200.0, 0.0), text="333", font_size=0.6, prefer=0.0),
    ]
    obstacles = Obstacles(markers=[], segments=[])
    positions, _collisions = solve_label_positions(labels, obstacles, 0.03)
    radius_one = math.hypot(*positions["one"])
    radius_two = math.hypot(positions["two"][0] - 100.0, positions["two"][1])
    radius_three = math.hypot(positions["three"][0] - 200.0, positions["three"][1])
    assert radius_one < radius_two < radius_three


def test_solving_twice_produces_identical_results() -> None:
    labels = [
        LabelRequest(key=i, anchor=(math.sin(i), math.cos(i) * 3.0), text=str(i), font_size=0.6, prefer=None)
        for i in range(12)
    ]
    obstacles = Obstacles(
        markers=[(l.anchor[0], l.anchor[1], 0.03) for l in labels],
        segments=[(labels[i].anchor, labels[i + 1].anchor) for i in range(len(labels) - 1)],
    )
    positions_a, collisions_a = solve_label_positions(labels, obstacles, 0.03)
    positions_b, collisions_b = solve_label_positions(labels, obstacles, 0.03)
    assert positions_a == positions_b
    assert collisions_a == collisions_b


def test_unresolved_count_grows_as_font_size_outgrows_a_tight_cluster() -> None:
    anchors = [(x * 0.1, y * 0.1) for x in range(3) for y in range(3)]
    unresolved_by_size = []
    for font_size in (0.01, 0.05, 0.2, 1.0, 5.0, 20.0):
        labels = [
            LabelRequest(key=i, anchor=a, text=str(i), font_size=font_size, prefer=None)
            for i, a in enumerate(anchors)
        ]
        obstacles = Obstacles(markers=[(a[0], a[1], 0.01) for a in anchors], segments=[])
        _positions, collisions = solve_label_positions(labels, obstacles, 0.01)
        unresolved_by_size.append(sum(1 for v in collisions.values() if v > 0))
    assert unresolved_by_size[0] == 0
    assert unresolved_by_size[-1] > 0


def test_returns_a_coordinate_for_every_label_even_when_fully_boxed_in() -> None:
    anchors = [(0.0, 0.0), (0.05, 0.0), (0.0, 0.05), (0.05, 0.05), (0.025, 0.09)]
    labels = [
        LabelRequest(key=i, anchor=a, text="8888", font_size=5.0, prefer=None) for i, a in enumerate(anchors)
    ]
    obstacles = Obstacles(markers=[(a[0], a[1], 0.02) for a in anchors], segments=[])
    positions, collisions = solve_label_positions(labels, obstacles, 0.02)
    assert set(positions) == {0, 1, 2, 3, 4}
    assert all(isinstance(v, tuple) and len(v) == 2 for v in positions.values())
    assert set(collisions) == {0, 1, 2, 3, 4}
