from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Hashable, List, Optional, Tuple

Point2D = Tuple[float, float]
Segment = Tuple[Point2D, Point2D]
Marker = Tuple[float, float, float]
Rect = Tuple[float, float, float, float]


@dataclass
class LabelRequest:
    key: Hashable
    anchor: Point2D
    text: str
    font_size: float
    prefer: Optional[float] = None


@dataclass
class Obstacles:
    markers: List[Marker]
    segments: List[Segment]


_RING_MULTIPLIERS = (1.0, 1.6, 2.4)
_DIRECTION_COUNT = 16
_TIGHT_GROUP_RADIUS_FACTOR = 3.0
_ON_SEGMENT_EPSILON = 1e-6
_MAX_SWEEPS = 60

_WEIGHT_MARKER = 1000.0
_WEIGHT_VORONOI = 900.0
_WEIGHT_LABEL = 600.0
_WEIGHT_SEGMENT = 400.0
_WEIGHT_RING = 8.0
_WEIGHT_ANGLE = 1.0
_WEIGHT_DISTANCE = 3.0


def _label_extent(font_size: float, text: str) -> Tuple[float, float]:
    width = 0.62 * font_size * len(text) + 0.30 * font_size
    height = 1.30 * font_size
    return width, height


def _rect_at(cx: float, cy: float, width: float, height: float) -> Rect:
    hw, hh = width / 2.0, height / 2.0
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _rect_circle_overlap(rect: Rect, circle: Marker) -> bool:
    x0, y0, x1, y1 = rect
    cx, cy, r = circle
    nx = min(max(cx, x0), x1)
    ny = min(max(cy, y0), y1)
    return math.hypot(cx - nx, cy - ny) < r


def _rect_rect_overlap(a: Rect, b: Rect) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _point_in_rect(p: Point2D, rect: Rect) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= p[0] <= x1 and y0 <= p[1] <= y1


def _segment_intersects_rect(seg: Segment, rect: Rect) -> bool:
    (x1, y1), (x2, y2) = seg
    if _point_in_rect((x1, y1), rect) or _point_in_rect((x2, y2), rect):
        return True
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return False
    x0, y0, x1r, y1r = rect
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - x0), (dx, x1r - x1), (-dy, y1 - y0), (dy, y1r - y1)):
        if p == 0.0:
            if q < 0.0:
                return False
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return False
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return False
            if r < t1:
                t1 = r
    return t0 <= t1


def _point_segment_distance(p: Point2D, seg: Segment) -> float:
    (x1, y1), (x2, y2) = seg
    px, py = p
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nx, ny = x1 + t * dx, y1 + t * dy
    return math.hypot(px - nx, py - ny)


def _find_incident_segment(anchor: Point2D, segments: List[Segment]) -> Optional[Segment]:
    for seg in segments:
        if _point_segment_distance(anchor, seg) <= _ON_SEGMENT_EPSILON:
            return seg
    return None


def _perpendicular_angle(seg: Segment) -> float:
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return math.atan2(dx, -dy)


def _angular_deviation(angle: float, prefer: float) -> float:
    diff = (angle - prefer + math.pi) % (2 * math.pi) - math.pi
    return abs(diff)


def _cluster_anchors(labels: List[LabelRequest]) -> Tuple[List[Point2D], Dict[Point2D, int], List[int]]:
    coords: List[Point2D] = []
    reach: List[float] = []
    index_of: Dict[Point2D, int] = {}
    for label in labels:
        anchor = label.anchor
        if anchor not in index_of:
            index_of[anchor] = len(coords)
            coords.append(anchor)
            reach.append(label.font_size)
        else:
            i = index_of[anchor]
            reach[i] = max(reach[i], label.font_size)

    n = len(coords)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            dist = math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])
            if dist <= _TIGHT_GROUP_RADIUS_FACTOR * max(reach[i], reach[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)

    roots = [find(i) for i in range(n)]
    return coords, index_of, roots


def _group_centroids(coords: List[Point2D], roots: List[int]) -> Dict[int, Tuple[float, float, int]]:
    sums: Dict[int, Tuple[float, float, int]] = {}
    for coord, root in zip(coords, roots):
        sx, sy, count = sums.get(root, (0.0, 0.0, 0))
        sums[root] = (sx + coord[0], sy + coord[1], count + 1)
    return sums


def _auto_prefer(
    anchor: Point2D,
    index_of: Dict[Point2D, int],
    roots: List[int],
    centroids: Dict[int, Tuple[float, float, int]],
    segments: List[Segment],
) -> float:
    coord_idx = index_of[anchor]
    root = roots[coord_idx]
    sx, sy, count = centroids[root]
    if count >= 2:
        gx, gy = sx / count, sy / count
        dx, dy = anchor[0] - gx, anchor[1] - gy
        if dx != 0.0 or dy != 0.0:
            return math.atan2(dy, dx)
    segment = _find_incident_segment(anchor, segments)
    if segment is not None:
        return _perpendicular_angle(segment)
    return 0.0


@dataclass
class _Candidate:
    x: float
    y: float
    rect: Rect
    ring: int
    angle: float
    radius: float


def _build_candidates(anchor: Point2D, width: float, height: float, marker_radius: float) -> List[_Candidate]:
    base_radius = marker_radius + math.hypot(width, height) / 2.0
    candidates: List[_Candidate] = []
    for ring, multiplier in enumerate(_RING_MULTIPLIERS):
        radius = base_radius * multiplier
        for direction in range(_DIRECTION_COUNT):
            angle = direction * (2.0 * math.pi / _DIRECTION_COUNT)
            x = anchor[0] + radius * math.cos(angle)
            y = anchor[1] + radius * math.sin(angle)
            candidates.append(_Candidate(x, y, _rect_at(x, y, width, height), ring, angle, radius))
    return candidates


def solve_label_positions(
    labels: List[LabelRequest],
    obstacles: Obstacles,
    marker_radius: float,
) -> Tuple[Dict[Hashable, Point2D], Dict[Hashable, int]]:
    n = len(labels)
    if n == 0:
        return {}, {}

    coords, index_of, roots = _cluster_anchors(labels)
    centroids = _group_centroids(coords, roots)

    extents = [_label_extent(label.font_size, label.text) for label in labels]
    effective_prefer = [
        label.prefer
        if label.prefer is not None
        else _auto_prefer(label.anchor, index_of, roots, centroids, obstacles.segments)
        for label in labels
    ]
    candidates = [
        _build_candidates(labels[i].anchor, extents[i][0], extents[i][1], marker_radius) for i in range(n)
    ]

    anchors = [label.anchor for label in labels]
    u_costs: List[List[float]] = []
    for i in range(n):
        prefer = effective_prefer[i]
        other_anchors = anchors[:i] + anchors[i + 1 :]
        row: List[float] = []
        for cand in candidates[i]:
            marker_hit = any(_rect_circle_overlap(cand.rect, m) for m in obstacles.markers)
            segment_hit = any(_segment_intersects_rect(s, cand.rect) for s in obstacles.segments)
            own_dist = math.hypot(cand.x - anchors[i][0], cand.y - anchors[i][1])
            voronoi_violation = any(
                math.hypot(cand.x - other[0], cand.y - other[1]) < own_dist for other in other_anchors
            )
            cost = (
                (_WEIGHT_MARKER if marker_hit else 0.0)
                + (_WEIGHT_VORONOI if voronoi_violation else 0.0)
                + (_WEIGHT_SEGMENT if segment_hit else 0.0)
                + _WEIGHT_RING * cand.ring
                + _WEIGHT_ANGLE * _angular_deviation(cand.angle, prefer)
                + _WEIGHT_DISTANCE * cand.radius
            )
            row.append(cost)
        u_costs.append(row)

    diagonals = [math.hypot(w, h) for w, h in extents]
    reach = [candidates[i][-1].radius + diagonals[i] / 2.0 for i in range(n)]
    neighbors: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = math.hypot(anchors[i][0] - anchors[j][0], anchors[i][1] - anchors[j][1])
            if dist <= reach[i] + reach[j]:
                neighbors[i].append(j)
                neighbors[j].append(i)

    assignment = [min(range(len(u_costs[i])), key=lambda c, i=i: u_costs[i][c]) for i in range(n)]

    for _sweep in range(_MAX_SWEEPS):
        changed = False
        for i in range(n):
            best_idx = assignment[i]
            best_cost = None
            for c, cand in enumerate(candidates[i]):
                cost = u_costs[i][c]
                for j in neighbors[i]:
                    other_rect = candidates[j][assignment[j]].rect
                    if _rect_rect_overlap(cand.rect, other_rect):
                        cost += _WEIGHT_LABEL
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_idx = c
            if best_idx != assignment[i]:
                assignment[i] = best_idx
                changed = True
        if not changed:
            break

    positions: Dict[Hashable, Point2D] = {}
    collisions: Dict[Hashable, int] = {}
    final_rects = [candidates[i][assignment[i]].rect for i in range(n)]
    for i in range(n):
        cand = candidates[i][assignment[i]]
        positions[labels[i].key] = (cand.x, cand.y)
        marker_count = sum(1 for m in obstacles.markers if _rect_circle_overlap(cand.rect, m))
        segment_count = sum(1 for s in obstacles.segments if _segment_intersects_rect(s, cand.rect))
        label_count = sum(1 for j in range(n) if j != i and _rect_rect_overlap(cand.rect, final_rects[j]))
        own_dist = math.hypot(cand.x - anchors[i][0], cand.y - anchors[i][1])
        voronoi_count = sum(
            1
            for j in range(n)
            if j != i and math.hypot(cand.x - anchors[j][0], cand.y - anchors[j][1]) < own_dist
        )
        collisions[labels[i].key] = marker_count + segment_count + label_count + (1 if voronoi_count else 0)

    return positions, collisions
