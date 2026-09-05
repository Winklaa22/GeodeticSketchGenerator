from __future__ import annotations

import random
import zlib
from typing import Dict, FrozenSet, List, Set, Tuple

import pytest

from core.route_graph import (
    EndpointType,
    JunctionClass,
    build_cable_chains,
    build_mst,
    build_outlines,
    build_route_graph,
    compute_sensitivity_margins,
    extend_with_delaunay_fallback,
)
from models.point import Point

Q = 0.01


def _coord(points: Dict[int, Point], number: int) -> Tuple[float, float]:
    point = points[number]
    return point.x, point.y


def _segments(edges: List[Tuple[int, int]], points: Dict[int, Point]) -> Set[FrozenSet[Tuple[float, float]]]:
    return {frozenset((_coord(points, a), _coord(points, b))) for a, b in edges}


def _assert_same_segments(actual_edges, points, expected_edges, expected_points=None) -> None:
    expected_points = expected_points if expected_points is not None else points
    actual = _segments(actual_edges, points)
    expected = _segments(expected_edges, expected_points)
    missing = expected - actual
    false_positive = actual - expected
    assert not missing, f"missing segments: {missing}"
    assert not false_positive, f"unexpected segments: {false_positive}"


def _rectangle(base: int, cx: float, cy: float, centre_offset: Tuple[float, float] = (0.02, 0.01)) -> Dict[int, Point]:
    ox, oy = centre_offset
    return {
        base: Point(cx - 0.5, cy - 0.5, 0.0),
        base + 1: Point(cx + 0.5, cy - 0.5, 0.0),
        base + 2: Point(cx + 0.5, cy + 0.5, 0.0),
        base + 3: Point(cx - 0.5, cy + 0.5, 0.0),
        base + 4: Point(cx + ox, cy + oy, 0.0),
    }


def _chain_fixture() -> Dict[int, Point]:
    return {i: Point(float(i) * 10.0, 0.0, 0.0) for i in range(1, 6)}


def _tap_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0))
    points.update(_rectangle(6, 20.0, 0.0))
    points[11] = Point(0.0, 0.0, 0.0)
    points[12] = Point(0.0, 10.0, 0.0)
    return points


def _convergence_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0))
    points[6] = Point(0.0, 0.0, 0.0)
    points[7] = Point(0.0, 10.0, 0.0)
    points[8] = Point(0.0, -10.0, 0.0)
    return points


def _distribution_node_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0))
    points.update(_rectangle(6, 20.0, 0.0))
    points.update(_rectangle(11, 0.0, 20.0))
    points[16] = Point(0.0, 0.0, 0.0)
    return points


def _degree_four_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0))
    points.update(_rectangle(6, 20.0, 0.0))
    points.update(_rectangle(11, 0.0, 20.0))
    points.update(_rectangle(16, 0.0, -20.0))
    points[21] = Point(0.0, 0.0, 0.0)
    return points


def _artefact_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(6, 20.0, 0.0, centre_offset=(0.0, 0.0)))
    points[11] = Point(0.0, 0.0, 0.0)
    points[12] = Point(0.0, 0.02, 0.0)
    return points


def _junction_to_junction_fixture() -> Dict[int, Point]:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(6, 20.0, 0.0, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(11, 0.0, 40.0, centre_offset=(0.0, 0.0)))
    points[16] = Point(0.0, 0.0, 0.0)
    points[17] = Point(0.0, 20.0, 0.0)
    points[18] = Point(-10.0, 20.0, 0.0)
    points[19] = Point(10.0, 20.0, 0.0)
    return points


def _ring_fixture() -> Dict[int, Point]:
    return {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(10.0, 10.0, 0.0),
        4: Point(0.0, 10.0, 0.0),
    }


def test_plain_chain_has_no_outlines_and_no_junctions() -> None:
    points = _chain_fixture()
    graph = build_route_graph(points, q=Q)
    assert graph.outlines == []
    assert graph.junctions == {}
    _assert_same_segments(graph.edges, points, [(1, 2), (2, 3), (3, 4), (4, 5)])


def test_rectangle_with_offset_centre_is_detected_and_centre_need_not_be_equidistant_from_corners() -> None:
    points = _rectangle(1, 0.0, 0.0, centre_offset=(0.3, 0.35))
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert outlines == [(1, 2, 3, 4)]
    assert centres == {5: 0}
    assert corners == {1, 2, 3, 4}


def test_rectangle_corners_are_ordered_cyclically_not_by_side_length() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(1.0, 1.0, 0.0),
        3: Point(1.0, 0.0, 0.0),
        4: Point(0.0, 1.0, 0.0),
        5: Point(0.5, 0.5, 0.0),
    }
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert outlines == [(1, 3, 2, 4)]
    assert centres == {5: 0}


def test_two_non_overlapping_rectangles_both_resolve() -> None:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, 0.0, 0.0))
    points.update(_rectangle(6, 50.0, 0.0))
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert set(outlines) == {(1, 2, 3, 4), (6, 7, 8, 9)}
    assert centres == {5: outlines.index((1, 2, 3, 4)), 10: outlines.index((6, 7, 8, 9))}
    assert corners == {1, 2, 3, 4, 6, 7, 8, 9}


def test_overlapping_rectangle_candidate_resolves_to_the_smaller_closure_error_one() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(1.0, 0.0, 0.0),
        3: Point(1.0, 1.0, 0.0),
        4: Point(0.0, 1.0, 0.0),
        5: Point(0.5, 0.5, 0.0),
        6: Point(1.0 + 3 * Q, 0.0, 0.0),
    }
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert (1, 2, 3, 4) in outlines
    assert centres.get(5) is not None
    assert 6 not in corners


def test_rectangle_candidate_with_diagonal_over_r_max_is_rejected() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(3.0, 0.0, 0.0),
        3: Point(3.0, 3.0, 0.0),
        4: Point(0.0, 3.0, 0.0),
        5: Point(1.5, 1.5, 0.0),
    }
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert outlines == []
    assert corners == set()


def test_rectangle_with_sides_below_the_degenerate_floor_is_rejected() -> None:
    tiny = 10 * Q
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(tiny, 0.0, 0.0),
        3: Point(tiny, tiny, 0.0),
        4: Point(0.0, tiny, 0.0),
        5: Point(tiny / 2, tiny / 2, 0.0),
    }
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert outlines == []


def test_rectangle_with_more_than_one_interior_point_is_rejected_entirely() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(1.0, 0.0, 0.0),
        3: Point(1.0, 1.0, 0.0),
        4: Point(0.0, 1.0, 0.0),
        5: Point(0.5, 0.5, 0.0),
        6: Point(0.4, 0.5, 0.0),
    }
    outlines, centres, corners = build_outlines(points, tol_outline=3 * Q)
    assert outlines == []
    assert centres == {}
    assert corners == set()


def test_rectangle_corners_are_excluded_from_mst_point_set_but_centre_is_not() -> None:
    points = _tap_fixture()
    graph = build_route_graph(points, q=Q)
    used = {n for edge in graph.edges for n in edge}
    assert used.isdisjoint({1, 2, 3, 4, 6, 7, 8, 9})
    assert {5, 10} <= used


def test_mst_never_connects_points_by_consecutive_number() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(100.0, 0.0, 0.0),
        3: Point(3.41, 0.0, 0.0),
        4: Point(200.0, 0.0, 0.0),
    }
    edges = build_mst(points)
    assert (1, 3) in edges or (3, 1) in edges
    assert (1, 2) not in edges and (2, 1) not in edges


def test_mst_is_a_spanning_tree_with_no_cycles_for_the_chain_fixture() -> None:
    points = _chain_fixture()
    edges = build_mst(points)
    assert len(edges) == len(points) - 1


def test_sensitivity_margins_flags_a_near_tie_edge() -> None:
    points = {
        1: Point(0.0, 0.0, 0.0),
        2: Point(10.0, 0.0, 0.0),
        3: Point(20.0, 0.0, 0.0),
        4: Point(10.0, 0.1, 0.0),
    }
    edges = build_mst(points)
    margins = compute_sensitivity_margins(points, edges, flag_threshold=3 * Q)
    assert any(m.flagged for m in margins)


def test_sensitivity_margins_reports_a_large_unflagged_margin_for_an_unambiguous_chain() -> None:
    points = _chain_fixture()
    edges = build_mst(points)
    margins = compute_sensitivity_margins(points, edges, flag_threshold=3 * Q)
    assert margins
    assert all(not m.flagged for m in margins)


def test_delaunay_fallback_is_off_by_default_even_when_a_short_cross_edge_exists() -> None:
    points = _ring_fixture()
    graph = build_route_graph(points, q=Q)
    assert len(graph.edges) == 3


def test_delaunay_fallback_adds_the_expected_extra_edge_for_the_ring_fixture_when_enabled() -> None:
    points = _ring_fixture()
    graph = build_route_graph(points, q=Q, include_delaunay_fallback=True)
    assert len(graph.edges) > 3
    edges = extend_with_delaunay_fallback(points, build_mst(points), k=1.5)
    assert set(graph.edges) == set(edges)


def test_tap_fixture_classifies_as_tap_with_one_free_end_and_two_enclosures() -> None:
    points = _tap_fixture()
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[11]
    assert info.classification is JunctionClass.TAP
    types = sorted(a.endpoint_type.name for a in info.arms)
    assert types == ["ENCLOSURE", "ENCLOSURE", "FREE_END"]


def test_convergence_fixture_classifies_as_convergence_with_two_free_ends_and_one_enclosure() -> None:
    points = _convergence_fixture()
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[6]
    assert info.classification is JunctionClass.CONVERGENCE
    types = sorted(a.endpoint_type.name for a in info.arms)
    assert types == ["ENCLOSURE", "FREE_END", "FREE_END"]


def test_distribution_node_fixture_classifies_as_distribution_node_with_zero_free_ends() -> None:
    points = _distribution_node_fixture()
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[16]
    assert info.classification is JunctionClass.DISTRIBUTION_NODE
    assert all(a.endpoint_type is EndpointType.ENCLOSURE for a in info.arms)


def test_degree_four_all_enclosure_junction_is_a_distribution_node() -> None:
    points = _degree_four_fixture()
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[21]
    assert len(info.arms) == 4
    assert info.classification is JunctionClass.DISTRIBUTION_NODE


def test_an_arm_ending_at_another_junction_counts_as_a_free_end_not_a_third_type() -> None:
    points = _junction_to_junction_fixture()
    graph = build_route_graph(points, q=Q)
    assert set(graph.junctions) == {16, 17}
    arm_16_to_17 = next(a for a in graph.junctions[16].arms if a.endpoint == 17)
    assert arm_16_to_17.endpoint_type is EndpointType.FREE_END


def test_short_arm_below_min_arm_forces_artefact_even_when_endpoint_pattern_matches_tap() -> None:
    points = _artefact_fixture()
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[11]
    assert info.classification is JunctionClass.ARTEFACT
    assert min(a.length for a in info.arms) < 5 * Q


def test_arm_length_is_the_summed_chain_length_not_just_the_first_hop_distance() -> None:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -20.0, 0.0, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(6, 20.0, 0.0, centre_offset=(0.0, 0.0)))
    points[11] = Point(0.0, 0.0, 0.0)
    points[12] = Point(0.0, 5.0, 0.0)
    points[13] = Point(0.0, 10.0, 0.0)
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[11]
    free_arm = next(a for a in info.arms if a.endpoint_type is EndpointType.FREE_END)
    assert free_arm.first_hop == 12
    assert free_arm.endpoint == 13
    assert free_arm.length == pytest.approx(10.0)


def test_junction_in_the_middle_of_a_run_is_detected_by_degree_alone() -> None:
    points = _tap_fixture()
    graph = build_route_graph(points, q=Q)
    assert 11 in graph.junctions


def test_angle_reporting_is_present_but_never_changes_classification() -> None:
    config_a = _tap_fixture()
    config_b: Dict[int, Point] = {}
    config_b.update(_rectangle(1, -20.0, 0.0))
    config_b.update(_rectangle(6, 20.0, 0.0))
    config_b[11] = Point(0.0, 0.0, 0.0)
    config_b[12] = Point(1.0, 10.0, 0.0)

    graph_a = build_route_graph(config_a, q=Q)
    graph_b = build_route_graph(config_b, q=Q)

    assert graph_a.junctions[11].classification is JunctionClass.TAP
    assert graph_b.junctions[11].classification is JunctionClass.TAP
    assert graph_a.junctions[11].largest_angles_deg != graph_b.junctions[11].largest_angles_deg


def test_inconclusive_flag_is_set_when_the_two_largest_angles_are_within_15_degrees() -> None:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, 20.0, 0.0, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(6, -10.0, 17.3, centre_offset=(0.0, 0.0)))
    points.update(_rectangle(11, -10.0, -17.3, centre_offset=(0.0, 0.0)))
    points[16] = Point(0.0, 0.0, 0.0)
    graph = build_route_graph(points, q=Q)
    info = graph.junctions[16]
    assert info.inconclusive is True


NOISE_FIXTURES = {
    "chain": _chain_fixture,
    "tap": _tap_fixture,
    "convergence": _convergence_fixture,
    "distribution_node": _distribution_node_fixture,
    "degree_four": _degree_four_fixture,
}


# A 500-trial calibration run at sigma = q/2 measured: chain (0 rectangles)
# 100.0%, convergence (1) 99.2%, tap (2) 98.6%, distribution_node (3) 97.2%,
# degree_four (4) 97.0% - stability drops as the number of independent,
# hard-threshold rectangle-detection gates in the fixture grows, matching
# the reference implementation's own reported real-world range of
# 97.4-99.6%. The floor asserted below is deliberately well under even the
# worst measured rate, purely to absorb this test's own smaller (200-trial)
# sampling noise without flaking - it is not itself the claimed stability.
NOISE_STABILITY_FLOOR = 180


@pytest.mark.parametrize("name", sorted(NOISE_FIXTURES))
def test_noise_perturbation_keeps_classification_stable(name: str) -> None:
    base_points = NOISE_FIXTURES[name]()
    base_graph = build_route_graph(base_points, q=Q)
    base_classes = {n: info.classification for n, info in base_graph.junctions.items()}

    random.seed(zlib.crc32(name.encode()))
    sigma = Q / 2
    trials = 200
    unchanged = 0
    for _ in range(trials):
        noisy = {
            n: Point(p.x + random.gauss(0, sigma), p.y + random.gauss(0, sigma), p.h) for n, p in base_points.items()
        }
        noisy_graph = build_route_graph(noisy, q=Q)
        noisy_classes = {n: info.classification for n, info in noisy_graph.junctions.items()}
        if noisy_classes == base_classes:
            unchanged += 1

    assert unchanged >= NOISE_STABILITY_FLOOR, f"{name}: only {unchanged}/{trials} trials unchanged"


PERMUTATION_FIXTURES = {
    "chain": _chain_fixture,
    "tap": _tap_fixture,
    "convergence": _convergence_fixture,
    "distribution_node": _distribution_node_fixture,
    "degree_four": _degree_four_fixture,
    "junction_to_junction": _junction_to_junction_fixture,
}


@pytest.mark.parametrize("name", sorted(PERMUTATION_FIXTURES))
def test_permutation_renumbering_reproduces_identical_graph_by_coordinates_every_time(name: str) -> None:
    base_points = PERMUTATION_FIXTURES[name]()
    base_graph = build_route_graph(base_points, q=Q)
    base_edges = _segments(base_graph.edges, base_points)
    base_outline_shapes = {tuple(_coord(base_points, n) for n in outline) for outline in base_graph.outlines}
    base_classes_by_coord = {
        _coord(base_points, number): info.classification for number, info in base_graph.junctions.items()
    }

    random.seed(zlib.crc32(name.encode()))
    keys = list(base_points)
    for _ in range(50):
        shuffled = keys[:]
        random.shuffle(shuffled)
        remap = dict(zip(keys, shuffled))
        permuted_points = {remap[k]: v for k, v in base_points.items()}

        graph = build_route_graph(permuted_points, q=Q)
        edges = _segments(graph.edges, permuted_points)
        outline_shapes = {tuple(_coord(permuted_points, n) for n in outline) for outline in graph.outlines}
        classes_by_coord = {
            _coord(permuted_points, number): info.classification for number, info in graph.junctions.items()
        }

        assert edges == base_edges
        assert outline_shapes == base_outline_shapes
        assert classes_by_coord == base_classes_by_coord


def test_build_cable_chains_keeps_a_plain_chain_as_one_chain() -> None:
    points = _chain_fixture()
    graph = build_route_graph(points, q=Q)
    chains = build_cable_chains(graph.edges, graph.junctions)
    assert chains == [[1, 2, 3, 4, 5]]


def test_build_cable_chains_merges_the_two_enclosure_arms_of_a_tap() -> None:
    points = _tap_fixture()
    graph = build_route_graph(points, q=Q)
    chains = build_cable_chains(graph.edges, graph.junctions)
    chain_sets = [set(chain) for chain in chains]
    assert {5, 11, 10} in chain_sets
    assert {11, 12} in chain_sets
    assert len(chains) == 2
    through_run = next(c for c in chains if set(c) == {5, 11, 10})
    assert through_run[1] == 11


def test_build_cable_chains_never_duplicates_an_edge_across_chains() -> None:
    points = _tap_fixture()
    graph = build_route_graph(points, q=Q)
    chains = build_cable_chains(graph.edges, graph.junctions)
    seen_edges: Set[FrozenSet[int]] = set()
    for chain in chains:
        for a, b in zip(chain, chain[1:]):
            edge = frozenset((a, b))
            assert edge not in seen_edges
            seen_edges.add(edge)
    assert seen_edges == {frozenset(e) for e in graph.edges}


def test_build_cable_chains_does_not_merge_across_convergence_or_distribution_node() -> None:
    for fixture in (_convergence_fixture, _distribution_node_fixture, _degree_four_fixture):
        points = fixture()
        graph = build_route_graph(points, q=Q)
        chains = build_cable_chains(graph.edges, graph.junctions)
        for junction_number in graph.junctions:
            arms_touching_junction = sum(1 for chain in chains if junction_number in chain)
            degree = sum(1 for a, b in graph.edges if a == junction_number or b == junction_number)
            assert arms_touching_junction == degree, fixture.__name__


def test_full_pipeline_on_a_mixed_chain_plus_tap_plus_rectangle_fixture() -> None:
    points: Dict[int, Point] = {}
    points.update(_rectangle(1, -40.0, 0.0))
    points[6] = Point(-20.0, 0.0, 0.0)
    points[7] = Point(0.0, 0.0, 0.0)
    points[8] = Point(0.0, 10.0, 0.0)
    points[9] = Point(20.0, 0.0, 0.0)
    points.update(_rectangle(10, 40.0, 0.0))

    graph = build_route_graph(points, q=Q)
    assert set(graph.outlines) == {(1, 2, 3, 4), (10, 11, 12, 13)}
    assert 7 in graph.junctions
    assert graph.junctions[7].classification is JunctionClass.TAP
