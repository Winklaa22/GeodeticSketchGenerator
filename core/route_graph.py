from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Iterable, List, Optional, Set, Tuple

from models.point import Point

# DOMAIN constant: physical size of a cable cabinet/enclosure. This is not
# derived from the data and does not need recalibration between jobs, but it
# does need revisiting for networks with larger structures such as manholes.
R_MAX = 2.00

# All geometry in this module is done in Point space (post file-X/Y-swap,
# atan2(dy, dx)) consistently, matching core/geometry.py's convention -
# never file space. Distances are invariant to the swap; the swap is a fixed
# reflection on bearings, which preserves every angle *difference* used
# below, so staying in one space throughout is safe.


class EndpointType(Enum):
    FREE_END = auto()
    ENCLOSURE = auto()


class JunctionClass(Enum):
    ARTEFACT = auto()
    TAP = auto()
    CONVERGENCE = auto()
    DISTRIBUTION_NODE = auto()
    UNCLASSIFIED = auto()


@dataclass(frozen=True)
class Arm:

    junction: int
    first_hop: int
    endpoint: int
    endpoint_type: EndpointType
    length: float
    direction_deg: float


@dataclass(frozen=True)
class JunctionInfo:

    number: int
    arms: Tuple[Arm, ...]
    classification: JunctionClass
    largest_angles_deg: Tuple[float, float]
    inconclusive: bool


@dataclass(frozen=True)
class RoutedGraph:

    edges: List[Tuple[int, int]]
    outlines: List[Tuple[int, ...]]
    centres: Dict[int, int]
    junctions: Dict[int, JunctionInfo]


@dataclass(frozen=True)
class EdgeMargin:

    edge: Tuple[int, int]
    weight: float
    alternative: Optional[Tuple[int, int]]
    margin: Optional[float]
    flagged: bool


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


_COINCIDENCE_EPSILON = 1e-9


@dataclass(frozen=True)
class _RectangleCandidate:

    corners: Tuple[int, int, int, int]
    centre: Optional[int]
    closure_error: float


def _spatial_grid(points: Dict[int, Point], cell_size: float) -> Dict[Tuple[int, int], List[int]]:
    grid: Dict[Tuple[int, int], List[int]] = {}
    for number, point in points.items():
        key = (math.floor(point.x / cell_size), math.floor(point.y / cell_size))
        grid.setdefault(key, []).append(number)
    return grid


def _forward_block_candidates(grid: Dict[Tuple[int, int], List[int]], key: Tuple[int, int]) -> List[int]:
    cx, cy = key
    numbers: List[int] = []
    for dx in (0, 1):
        for dy in (0, 1):
            numbers.extend(grid.get((cx + dx, cy + dy), []))
    return numbers


def _cyclic_order(quad: Tuple[int, int, int, int], points: Dict[int, Point]) -> List[int]:
    centroid_x = sum(points[n].x for n in quad) / 4.0
    centroid_y = sum(points[n].y for n in quad) / 4.0
    return sorted(quad, key=lambda n: math.atan2(points[n].y - centroid_y, points[n].x - centroid_x))


def _evaluate_rectangle(ordered: List[int], points: Dict[int, Point], tol_outline: float, r_max: float) -> Optional[float]:
    corner_points = [points[n] for n in ordered]
    for a, b in zip(corner_points, corner_points[1:] + corner_points[:1]):
        if _distance(a, b) < _COINCIDENCE_EPSILON:
            return None

    sides = [
        _distance(corner_points[k], corner_points[(k + 1) % 4])
        for k in range(4)
    ]
    diagonals = (
        _distance(corner_points[0], corner_points[2]),
        _distance(corner_points[1], corner_points[3]),
    )

    # Degenerate-side floor (min side >= 5 * tol_outline): matches the
    # reference implementation's guard against near-coincident points
    # trivially satisfying the equal-sides/equal-diagonals tests below.
    if min(sides) < 5 * tol_outline:
        return None
    if max(diagonals) > r_max:
        return None
    if abs(sides[0] - sides[2]) > tol_outline or abs(sides[1] - sides[3]) > tol_outline:
        return None
    if abs(diagonals[0] - diagonals[1]) > tol_outline:
        return None

    return abs(sides[0] - sides[2]) + abs(sides[1] - sides[3]) + abs(diagonals[0] - diagonals[1])


def _interior_points(ordered: List[int], candidates: Iterable[int], points: Dict[int, Point]) -> List[int]:
    corner_set = set(ordered)
    corner_points = [points[n] for n in ordered]
    interior: List[int] = []
    for number in candidates:
        if number in corner_set:
            continue
        point = points[number]
        signs = []
        for k in range(4):
            a, b = corner_points[k], corner_points[(k + 1) % 4]
            signs.append((b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x))
        if all(s >= 0 for s in signs) or all(s <= 0 for s in signs):
            interior.append(number)
    return interior


def _resolve_overlaps(candidates: List[_RectangleCandidate]) -> List[_RectangleCandidate]:
    accepted: List[_RectangleCandidate] = []
    claimed: Set[int] = set()
    for candidate in sorted(candidates, key=lambda c: c.closure_error):
        points_used = set(candidate.corners)
        if candidate.centre is not None:
            points_used.add(candidate.centre)
        if points_used & claimed:
            continue
        accepted.append(candidate)
        claimed |= points_used
    return accepted


def build_outlines(
    points: Dict[int, Point], tol_outline: float, r_max: float = R_MAX
) -> Tuple[List[Tuple[int, ...]], Dict[int, int], Set[int]]:
    grid = _spatial_grid(points, r_max)
    seen_quads: Set[frozenset] = set()
    candidates: List[_RectangleCandidate] = []

    for key in grid:
        block = _forward_block_candidates(grid, key)
        if len(block) < 4:
            continue
        for combo in itertools.combinations(block, 4):
            quad = frozenset(combo)
            if quad in seen_quads:
                continue
            seen_quads.add(quad)

            ordered = _cyclic_order(tuple(combo), points)
            closure_error = _evaluate_rectangle(ordered, points, tol_outline, r_max)
            if closure_error is None:
                continue

            interior = _interior_points(ordered, block, points)
            if len(interior) != 1:
                continue

            candidates.append(
                _RectangleCandidate(corners=tuple(ordered), centre=interior[0], closure_error=closure_error)
            )

    accepted = _resolve_overlaps(candidates)
    outlines = [candidate.corners for candidate in accepted]
    centres = {candidate.centre: index for index, candidate in enumerate(accepted) if candidate.centre is not None}
    corner_numbers = {n for candidate in accepted for n in candidate.corners}
    return outlines, centres, corner_numbers


class _UnionFind:

    def __init__(self, items: Iterable[int]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: int) -> int:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> bool:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        self._parent[root_a] = root_b
        return True


def build_mst(points: Dict[int, Point]) -> List[Tuple[int, int]]:
    numbers = list(points)
    if len(numbers) < 2:
        return []

    candidate_edges = sorted(
        (_distance(points[a], points[b]), a, b)
        for i, a in enumerate(numbers)
        for b in numbers[i + 1 :]
    )

    union_find = _UnionFind(numbers)
    edges: List[Tuple[int, int]] = []
    for _, a, b in candidate_edges:
        if union_find.union(a, b):
            edges.append((a, b))
    return edges


def _mst_adjacency(edges: List[Tuple[int, int]]) -> Dict[int, List[int]]:
    adjacency: Dict[int, List[int]] = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    return adjacency


def _split_components(edges: List[Tuple[int, int]], removed: Tuple[int, int]) -> Tuple[Set[int], Set[int]]:
    remaining = [e for e in edges if e != removed and e != (removed[1], removed[0])]
    adjacency = _mst_adjacency(remaining)
    for endpoint in removed:
        adjacency.setdefault(endpoint, [])

    visited: Set[int] = set()
    stack = [removed[0]]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, []))

    all_nodes = {n for edge in edges for n in edge}
    other = all_nodes - visited
    return visited, other


def compute_sensitivity_margins(
    points: Dict[int, Point], mst_edges: List[Tuple[int, int]], flag_threshold: float
) -> List[EdgeMargin]:
    margins: List[EdgeMargin] = []
    for edge in mst_edges:
        weight = _distance(points[edge[0]], points[edge[1]])
        side_a, side_b = _split_components(mst_edges, edge)

        best_alternative: Optional[Tuple[int, int]] = None
        best_distance: Optional[float] = None
        for a in side_a:
            for b in side_b:
                if (a, b) == edge or (b, a) == edge:
                    continue
                candidate_distance = _distance(points[a], points[b])
                if best_distance is None or candidate_distance < best_distance:
                    best_distance, best_alternative = candidate_distance, (a, b)

        margin = None if best_distance is None else best_distance - weight
        flagged = margin is not None and margin < flag_threshold
        margins.append(EdgeMargin(edge=edge, weight=weight, alternative=best_alternative, margin=margin, flagged=flagged))
    return margins


def extend_with_delaunay_fallback(
    points: Dict[int, Point], mst_edges: List[Tuple[int, int]], k: float = 1.5
) -> List[Tuple[int, int]]:
    # Labelled simplification: requirements.txt carries no numpy/scipy, so
    # true Delaunay triangulation is unavailable here. This scans all
    # non-tree pairs within k * median(tree edge length) instead of
    # restricting to Delaunay edges - it is not validated against any real
    # ring/parallel-route survey (none exists in this repo), and is kept
    # small and isolated so a real Delaunay implementation can replace it
    # later without touching build_route_graph's main path.
    if not mst_edges:
        return list(mst_edges)

    weights = sorted(_distance(points[a], points[b]) for a, b in mst_edges)
    mid = len(weights) // 2
    median = weights[mid] if len(weights) % 2 else (weights[mid - 1] + weights[mid]) / 2.0
    limit = k * median

    existing = {frozenset(edge) for edge in mst_edges}
    numbers = list(points)
    extra: List[Tuple[int, int]] = []
    for i, a in enumerate(numbers):
        for b in numbers[i + 1 :]:
            if frozenset((a, b)) in existing:
                continue
            if _distance(points[a], points[b]) <= limit:
                extra.append((a, b))

    return list(mst_edges) + extra


def _degree_map(edges: List[Tuple[int, int]]) -> Dict[int, int]:
    degrees: Dict[int, int] = {}
    for a, b in edges:
        degrees[a] = degrees.get(a, 0) + 1
        degrees[b] = degrees.get(b, 0) + 1
    return degrees


def find_junction_candidates(edges: List[Tuple[int, int]]) -> Set[int]:
    return {node for node, degree in _degree_map(edges).items() if degree >= 3}


def _tap_through_hops(junctions: Dict[int, JunctionInfo]) -> Dict[int, Tuple[int, int]]:
    # At a TAP, the two ENCLOSURE arms are one continuous trench passing
    # through the junction; the FREE_END arm is the branch tapping into it.
    # Every other junction class has no such unambiguous pairing (see
    # ALGORYTM.md KROK 6 - a real leaf-to-leaf cable assignment is only
    # unambiguous there because a TAP's classification already picks the
    # through-pair for us), so only TAP junctions get an entry here.
    through_hops: Dict[int, Tuple[int, int]] = {}
    for number, info in junctions.items():
        if info.classification is not JunctionClass.TAP:
            continue
        enclosure_hops = [arm.first_hop for arm in info.arms if arm.endpoint_type is EndpointType.ENCLOSURE]
        if len(enclosure_hops) == 2:
            through_hops[number] = (enclosure_hops[0], enclosure_hops[1])
    return through_hops


def _next_chain_hop(
    vertex: int,
    arrived_from: int,
    adjacency: Dict[int, List[int]],
    degrees: Dict[int, int],
    through_hops: Dict[int, Tuple[int, int]],
) -> Optional[int]:
    pair = through_hops.get(vertex)
    if pair is not None:
        a, b = pair
        if arrived_from == a:
            return b
        if arrived_from == b:
            return a
        return None
    if degrees.get(vertex, 0) != 2:
        return None
    neighbours = adjacency[vertex]
    return neighbours[0] if neighbours[1] == arrived_from else neighbours[1]


def _extend_chain(
    start: int,
    first_hop: int,
    adjacency: Dict[int, List[int]],
    degrees: Dict[int, int],
    through_hops: Dict[int, Tuple[int, int]],
) -> List[int]:
    tail = [first_hop]
    seen = {start, first_hop}
    previous, current = start, first_hop
    while True:
        next_node = _next_chain_hop(current, previous, adjacency, degrees, through_hops)
        if next_node is None or next_node in seen:
            break
        seen.add(next_node)
        tail.append(next_node)
        previous, current = current, next_node
    return tail


def build_cable_chains(edges: List[Tuple[int, int]], junctions: Dict[int, JunctionInfo]) -> List[List[int]]:
    adjacency = _mst_adjacency(edges)
    degrees = _degree_map(edges)
    through_hops = _tap_through_hops(junctions)

    visited_edges: Set[frozenset] = set()
    chains: List[List[int]] = []
    for a, b in edges:
        edge_key = frozenset((a, b))
        if edge_key in visited_edges:
            continue
        backward = _extend_chain(b, a, adjacency, degrees, through_hops)
        forward = _extend_chain(a, b, adjacency, degrees, through_hops)
        chain = list(reversed(backward)) + forward
        for x, y in zip(chain, chain[1:]):
            visited_edges.add(frozenset((x, y)))
        chains.append(chain)
    return chains


def _raw_bearing_deg(a: Point, b: Point) -> float:
    return math.degrees(math.atan2(b.y - a.y, b.x - a.x))


def _walk_arm(
    junction: int, first_hop: int, adjacency: Dict[int, List[int]], centres: Dict[int, int], points: Dict[int, Point]
) -> Arm:
    length = _distance(points[junction], points[first_hop])
    direction_deg = _raw_bearing_deg(points[junction], points[first_hop])

    previous, current = junction, first_hop
    # A centre stops the walk even at degree 2, since it is a physical
    # enclosure endpoint regardless of whether the route continues past it -
    # the reference implementation never needed this because its validated
    # cabinets are always degree-1 leaves.
    while current not in centres and len(adjacency.get(current, [])) == 2:
        neighbours = adjacency[current]
        next_node = neighbours[0] if neighbours[1] == previous else neighbours[1]
        length += _distance(points[current], points[next_node])
        previous, current = current, next_node

    endpoint_type = EndpointType.ENCLOSURE if current in centres else EndpointType.FREE_END
    return Arm(
        junction=junction,
        first_hop=first_hop,
        endpoint=current,
        endpoint_type=endpoint_type,
        length=length,
        direction_deg=direction_deg,
    )


def find_arms(
    junction: int, adjacency: Dict[int, List[int]], centres: Dict[int, int], points: Dict[int, Point]
) -> List[Arm]:
    return [_walk_arm(junction, neighbour, adjacency, centres, points) for neighbour in adjacency.get(junction, [])]


def _classify(arms: List[Arm], min_arm: float) -> JunctionClass:
    if any(arm.length < min_arm for arm in arms):
        return JunctionClass.ARTEFACT

    free_ends = [arm for arm in arms if arm.endpoint_type is EndpointType.FREE_END]
    enclosures = [arm for arm in arms if arm.endpoint_type is EndpointType.ENCLOSURE]

    if not free_ends:
        return JunctionClass.DISTRIBUTION_NODE
    if len(free_ends) == 1 and len(enclosures) == 2:
        return JunctionClass.TAP
    if len(free_ends) == 2 and len(enclosures) == 1:
        return JunctionClass.CONVERGENCE
    return JunctionClass.UNCLASSIFIED


def _angle_between(bearing_a: float, bearing_b: float) -> float:
    delta = abs(bearing_a - bearing_b) % 360.0
    return 360.0 - delta if delta > 180.0 else delta


def _largest_two_angles(arms: List[Arm]) -> Tuple[float, float]:
    angles = sorted(
        (_angle_between(a.direction_deg, b.direction_deg) for i, a in enumerate(arms) for b in arms[i + 1 :]),
        reverse=True,
    )
    if not angles:
        return 0.0, 0.0
    largest = angles[0]
    second = angles[1] if len(angles) > 1 else 0.0
    return largest, second


def build_route_graph(
    points: Dict[int, Point],
    q: float,
    include_delaunay_fallback: bool = False,
    delaunay_k: float = 1.5,
) -> RoutedGraph:
    if len(points) < 2:
        return RoutedGraph(edges=[], outlines=[], centres={}, junctions={})

    tol_outline = 3 * q
    min_arm = 5 * q

    outlines, centres, corner_numbers = build_outlines(points, tol_outline)

    remaining = {n: p for n, p in points.items() if n not in corner_numbers}
    mst_edges = build_mst(remaining)
    edges = extend_with_delaunay_fallback(remaining, mst_edges, delaunay_k) if include_delaunay_fallback else mst_edges

    adjacency = _mst_adjacency(edges)
    junction_numbers = find_junction_candidates(edges)

    junctions: Dict[int, JunctionInfo] = {}
    for number in junction_numbers:
        arms = find_arms(number, adjacency, centres, remaining)
        classification = _classify(arms, min_arm)
        largest, second = _largest_two_angles(arms)
        junctions[number] = JunctionInfo(
            number=number,
            arms=tuple(arms),
            classification=classification,
            largest_angles_deg=(largest, second),
            inconclusive=(largest - second) < 15.0,
        )

    return RoutedGraph(edges=edges, outlines=outlines, centres=centres, junctions=junctions)
