from __future__ import annotations

import math
from typing import Callable, Dict, List, Set, Tuple

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

CABINET_LABEL_COUNT = 6


def build_points_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    options = config.points
    radius = max(options.diameter / 2.0, 0.0)
    cabinet_targets = _cabinet_targets(selected_numbers, config.cabinet_mode)

    commands = []
    for direction in iter_point_directions(points, selected_numbers):
        point = direction.point
        commands.append(AddCircleCommand((point.x, point.y, point.h), radius, layer))
        if options.numbers_enabled:
            commands.append(
                _points_label_command(direction, options.font_size, config.cabinet_mode, cabinet_targets, layer)
            )
    return CompositeCommand(commands)


def _cabinet_targets(selected_numbers: List[int], cabinet_mode: bool) -> Set[int]:
    if not cabinet_mode:
        return set()
    return set(sorted(selected_numbers)[-CABINET_LABEL_COUNT:])


def _points_label_command(
    direction: PointDirection, font_size: float, cabinet_mode: bool, cabinet_targets: Set[int], layer: str
) -> AddTextCommand:
    point = direction.point
    x_offset, y_offset = _points_label_offset(direction.angle_deg, font_size)
    size = font_size
    if cabinet_mode and direction.number in cabinet_targets:
        size = font_size / 2.0
        x_offset = 0.0
        y_offset = 0.0
    insert = (point.x + x_offset, point.y + y_offset, point.h)
    return AddTextCommand(str(direction.number), insert, size, layer)


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
