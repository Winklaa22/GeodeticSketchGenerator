from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from core.commands.composite import CompositeCommand
from core.commands.draw import (
    AddCircleCommand,
    AddLineCommand,
    AddPolyline2DCommand,
    AddPolyline3DCommand,
    AddTextCommand,
)
from core.config import CableOptions, GenerationConfig
from core.draw_modes import DrawMode
from core.geometry import (
    AngleQuadrant,
    PointDirection,
    classify_quadrant,
    compute_direction_angle,
    iter_point_directions,
    offset_segment_perpendicular,
    snap_small_rotation,
)
from core.patterns import route_selected_points
from models.point import Point

def build_points_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    options = config.points
    radius = max(options.diameter / 2.0, 0.0)
    directions = list(iter_point_directions(points, selected_numbers))
    cabinet_offsets: Dict[int, Tuple[float, float]] = {}
    if options.numbers_enabled:
        for cluster in _cabinet_clusters(points, selected_numbers):
            cabinet_offsets.update(_cabinet_label_offsets(cluster, options.font_size))

    commands = []
    for direction in directions:
        point = direction.point
        commands.append(AddCircleCommand((point.x, point.y, point.h), radius, layer))
        if options.numbers_enabled:
            commands.append(
                _points_label_command(direction, options.font_size, cabinet_offsets, layer)
            )
    return CompositeCommand(commands)


def _cabinet_clusters(points: Dict[int, Point], selected_numbers: List[int]) -> List[Dict[int, Point]]:
    routed = route_selected_points(points, selected_numbers)
    number_by_id = {id(p): n for n, p in points.items()}

    clusters = [{number_by_id[id(p)]: p for p in box} for box in routed.boxes]
    clusters.extend({number_by_id[id(p)]: p for p in wedge} for wedge in routed.wedges)

    for cluster in clusters:
        centroid = _centroid(list(cluster.values()))
        if centroid is None:
            continue
        cluster_radius = max(math.hypot(p.x - centroid[0], p.y - centroid[1]) for p in cluster.values())
        for point in routed.main:
            number = number_by_id[id(point)]
            if number in cluster:
                continue
            if math.hypot(point.x - centroid[0], point.y - centroid[1]) <= cluster_radius:
                cluster[number] = point

    return clusters


def _centroid(points: List[Point]) -> Optional[Tuple[float, float]]:
    if not points:
        return None
    return sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points)


_CABINET_OFFSET_SCALES = (1.0, 1.5, 2.0, 2.5, 3.0)
_GLYPH_WIDTH_FACTOR = 0.9
_GLYPH_HEIGHT_FACTOR = 1.3


def _cabinet_label_offsets(cabinet_points: Dict[int, Point], font_size: float) -> Dict[int, Tuple[float, float]]:
    centroid = _centroid(list(cabinet_points.values()))
    if centroid is None:
        return {}
    half = font_size / 2.0
    centroid_x, centroid_y = centroid
    distances = {
        n: math.hypot(p.x - centroid_x, p.y - centroid_y) for n, p in cabinet_points.items()
    }
    ordering = sorted(cabinet_points, key=lambda n: distances[n], reverse=True)

    offsets: Dict[int, Tuple[float, float]] = {}
    placed_boxes: List[Tuple[float, float, float, float]] = []
    for number in ordering:
        point = cabinet_points[number]
        footprint = _label_footprint(str(number), font_size)
        x_sign = 1.0 if point.x >= centroid_x else -1.0
        y_sign = 1.0 if point.y >= centroid_y else -1.0

        best_offset = (half * x_sign, half * y_sign)
        best_overlaps = None
        for scale in _CABINET_OFFSET_SCALES:
            magnitude = half * scale
            candidates = [
                (magnitude * x_sign, magnitude * y_sign),
                (-magnitude * x_sign, magnitude * y_sign),
                (magnitude * x_sign, -magnitude * y_sign),
                (-magnitude * x_sign, -magnitude * y_sign),
                (magnitude, 0.0), (-magnitude, 0.0), (0.0, magnitude), (0.0, -magnitude),
            ]
            for candidate in candidates:
                box = _offset_bbox(point.x, point.y, candidate, footprint)
                overlaps = sum(1 for placed_box in placed_boxes if _boxes_overlap(box, placed_box))
                if best_overlaps is None or overlaps < best_overlaps:
                    best_offset, best_overlaps = candidate, overlaps
            if best_overlaps == 0:
                break

        offsets[number] = best_offset
        placed_boxes.append(_offset_bbox(point.x, point.y, best_offset, footprint))

    return offsets


def _label_footprint(text: str, size: float) -> Tuple[float, float]:
    return _GLYPH_WIDTH_FACTOR * size * len(text), _GLYPH_HEIGHT_FACTOR * size


def _offset_bbox(
    x: float, y: float, offset: Tuple[float, float], footprint: Tuple[float, float]
) -> Tuple[float, float, float, float]:
    x_offset, y_offset = offset
    width, height = footprint
    if x_offset > 0:
        x0, x1 = x + x_offset, x + x_offset + width
    elif x_offset < 0:
        x0, x1 = x + x_offset - width, x + x_offset
    else:
        x0, x1 = x - width, x + width
    if y_offset > 0:
        y0, y1 = y + y_offset, y + y_offset + height
    elif y_offset < 0:
        y0, y1 = y + y_offset - height, y + y_offset
    else:
        y0, y1 = y - height, y + height
    return x0, y0, x1, y1


def _boxes_overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _points_label_command(
    direction: PointDirection, font_size: float, cabinet_offsets: Dict[int, Tuple[float, float]], layer: str
) -> AddTextCommand:
    point = direction.point
    size = font_size
    cabinet_offset = cabinet_offsets.get(direction.number)
    if cabinet_offset is not None:
        x_offset, y_offset = cabinet_offset
        halign, valign = _text_anchor(x_offset, y_offset)
    else:
        x_offset, y_offset = _points_label_offset(direction.angle_deg, size)
        halign, valign = "left", "bottom"
    insert = (point.x + x_offset, point.y + y_offset, point.h)
    return AddTextCommand(str(direction.number), insert, size, layer, halign=halign, valign=valign)


def _text_anchor(x_offset: float, y_offset: float) -> Tuple[str, str]:
    if x_offset > 0:
        halign = "left"
    elif x_offset < 0:
        halign = "right"
    else:
        halign = "center"
    if y_offset > 0:
        valign = "bottom"
    elif y_offset < 0:
        valign = "top"
    else:
        valign = "middle"
    return halign, valign


def _points_label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
    half = font_size / 2.0
    offsets = {
        AngleQuadrant.NORTH_EAST: (half, -half),
        AngleQuadrant.NORTH_WEST: (-half, half),
        AngleQuadrant.SOUTH_WEST: (-half, -half),
        AngleQuadrant.SOUTH_EAST: (-half, half),
    }
    return offsets[classify_quadrant(angle_deg)]


def build_lines_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    routed = route_selected_points(points, selected_numbers)
    commands = [
        AddLineCommand((a.x, a.y, a.h), (b.x, b.y, b.h), layer) for a, b in zip(routed.main, routed.main[1:])
    ]
    commands.extend(_box_line_commands(routed.boxes, layer))
    commands.extend(_wedge_line_commands(routed.wedges, layer))
    return CompositeCommand(commands)


def _box_line_commands(boxes: List[List[Point]], layer: str) -> List[AddLineCommand]:
    commands = []
    for box in boxes:
        commands.extend(
            AddLineCommand(
                (box[k].x, box[k].y, box[k].h),
                (box[(k + 1) % len(box)].x, box[(k + 1) % len(box)].y, box[(k + 1) % len(box)].h),
                layer,
            )
            for k in range(len(box))
        )
    return commands


def _wedge_line_commands(wedges: List[Tuple[Point, Point, Point]], layer: str) -> List[AddLineCommand]:
    commands = []
    for entry, wing_1, wing_2 in wedges:
        commands.append(AddLineCommand((entry.x, entry.y, entry.h), (wing_1.x, wing_1.y, wing_1.h), layer))
        commands.append(AddLineCommand((entry.x, entry.y, entry.h), (wing_2.x, wing_2.y, wing_2.h), layer))
    return commands


def build_pipe_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    half_width = max(config.pipe.width, 0.0) / 2.0
    main = route_selected_points(points, selected_numbers).main
    commands = []
    for start, end in zip(main, main[1:]):
        for offset in (half_width, -half_width):
            a, b = offset_segment_perpendicular(start, end, offset)
            commands.append(AddLineCommand((a.x, a.y, a.h), (b.x, b.y, b.h), layer))
    return CompositeCommand(commands)


def build_plines_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    routed = route_selected_points(points, selected_numbers)
    commands = [AddPolyline2DCommand([(p.x, p.y) for p in routed.main], layer)]
    commands.extend(
        AddPolyline2DCommand([(p.x, p.y) for p in box], layer, closed=True) for box in routed.boxes
    )
    commands.extend(_wedge_line_commands(routed.wedges, layer))
    return CompositeCommand(commands)


def build_poly3d_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    routed = route_selected_points(points, selected_numbers)
    commands = [AddPolyline3DCommand([(p.x, p.y, p.h) for p in routed.main], layer)]
    commands.extend(
        AddPolyline3DCommand([(p.x, p.y, p.h) for p in box], layer, closed=True) for box in routed.boxes
    )
    commands.extend(_wedge_line_commands(routed.wedges, layer))
    return CompositeCommand(commands)


def build_heights_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    options = config.heights
    commands = []
    for direction in iter_point_directions(points, selected_numbers):
        if direction.number % options.frequency != 0:
            continue
        point = direction.point
        x_offset, y_offset = _direction_label_offset(direction.angle_deg, options.font_size)
        rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
        rounded_height = math.ceil(point.h * 10) / 10
        insert = (point.x + x_offset, point.y + y_offset, point.h)
        commands.append(AddTextCommand(str(rounded_height), insert, options.font_size, layer, rotation))
    return CompositeCommand(commands)


def _direction_label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
    half = font_size / 2.0
    offsets = {
        AngleQuadrant.NORTH_EAST: (half, 0.5),
        AngleQuadrant.NORTH_WEST: (-0.5, half),
        AngleQuadrant.SOUTH_WEST: (-half, -0.5),
        AngleQuadrant.SOUTH_EAST: (0.5, -half),
    }
    return offsets[classify_quadrant(angle_deg)]


def build_cable_marks_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    options = config.cable
    routed = route_selected_points(points, selected_numbers)
    segments = list(zip(routed.main, routed.main[1:]))
    mark_indices = _cable_mark_indices(len(segments), options.frequency) if segments else []
    return CompositeCommand([_cable_mark_command(segments[index], options, layer) for index in mark_indices])


def _cable_mark_indices(segment_count: int, frequency: int) -> List[int]:
    step = max(1, frequency)
    center = (segment_count - 1) // 2
    indices = {center}
    offset = step
    while True:
        added = False
        if center + offset < segment_count:
            indices.add(center + offset)
            added = True
        if center - offset >= 0:
            indices.add(center - offset)
            added = True
        if not added:
            break
        offset += step
    return sorted(indices)


def _cable_mark_command(segment: Tuple[Point, Point], options: CableOptions, layer: str) -> AddTextCommand:
    start, end = segment
    angle_deg = compute_direction_angle(start, end)
    mid_x = (start.x + end.x) / 2.0
    mid_y = (start.y + end.y) / 2.0
    x_offset, y_offset = _cable_label_offset(angle_deg, options.font_size)
    rotation = snap_small_rotation(angle_deg, round(angle_deg, 1))
    insert = (mid_x + x_offset, mid_y + y_offset, start.h)
    return AddTextCommand(options.marks_text, insert, options.font_size, layer, rotation)


def _cable_label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
    half = font_size / 2.0
    offsets = {
        AngleQuadrant.NORTH_EAST: (half, 0.0),
        AngleQuadrant.NORTH_WEST: (0.0, half),
        AngleQuadrant.SOUTH_WEST: (-half, 0.0),
        AngleQuadrant.SOUTH_EAST: (0.0, -half),
    }
    return offsets[classify_quadrant(angle_deg)]


SurveyBuilder = Callable[[Dict[int, Point], List[int], GenerationConfig, str], CompositeCommand]

_BUILDERS: Dict[DrawMode, SurveyBuilder] = {
    DrawMode.POINTS: build_points_command,
    DrawMode.LINES: build_lines_command,
    DrawMode.PLINES: build_plines_command,
    DrawMode.POLY3D: build_poly3d_command,
    DrawMode.HEIGHTS: build_heights_command,
    DrawMode.CABLE_MARKS: build_cable_marks_command,
    DrawMode.PIPE: build_pipe_command,
}


def get_survey_builder(draw_mode: DrawMode) -> SurveyBuilder:
    try:
        return _BUILDERS[draw_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported draw mode: {draw_mode!r}") from exc
