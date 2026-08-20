"""Composite "draw mode" commands — the direct-to-DXF replacement for the
app's original six .scr script-generation strategies. Each builder takes the
parsed survey points, the selected point numbers, and the same
`GenerationConfig` the option tabs already build, and returns one
`CompositeCommand` ready to run through `CommandHistory` — so one button
press is one undo step, no matter how many entities it creates.

The per-point offset/direction/quadrant math is unchanged from the original
strategies and still lives in `core/geometry.py`; only the *output* changed —
from formatted .scr text lines to real DXF entities via `core/commands/draw.py`.
"""
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
    """One CIRCLE at each selected point, with an optional number-label TEXT
    offset away from the point's direction of travel so the label doesn't
    overlap the line. In "cabinet mode", the last 6 selected labels are
    drawn smaller and without an offset."""
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
    """A chain of LINE entities through consecutive selected points, plus
    any skrzynka/wcinka shape along the way as its own LINE entities (see
    core.patterns)."""
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
    """Two parallel LINE entities per segment, straddling the routed cable
    path by config.pipe.width/2 on each side — a protective casing pipe
    (RURA OSŁONOWA) drawn alongside the cable run."""
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
    """A single 2D LWPOLYLINE through the selected points (XY only). Any
    skrzynka is its own separate closed LWPOLYLINE; any wcinka is two open
    stub LINEs off its entry point (see core.patterns)."""
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
    """A single 3D POLYLINE through the selected points (X, Y, height). Any
    skrzynka is its own separate closed 3D POLYLINE; any wcinka is two open
    stub LINEs off its entry point (see core.patterns)."""
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
    """A TEXT label with the rounded-up height value at every Nth selected
    point (N = config.heights.frequency), offset away from the point's
    direction of travel."""
    options = config.heights
    commands = []
    for direction in iter_point_directions(points, selected_numbers):
        if direction.number % options.frequency != 0:
            continue
        point = direction.point
        x_offset, y_offset = _heights_label_offset(direction.angle_deg, options.font_size)
        rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
        rounded_height = math.ceil(point.h * 10) / 10
        insert = (point.x + x_offset, point.y + y_offset, point.h)
        commands.append(AddTextCommand(str(rounded_height), insert, options.font_size, layer, rotation))
    return CompositeCommand(commands)


def _heights_label_offset(angle_deg: float, font_size: float) -> Tuple[float, float]:
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
    """The cable itself (see core.patterns), plus a TEXT label
    (config.cable.marks_text) at the midpoint of its centre segment, then
    fanning outward every Nth segment (config.cable.frequency). Each marked
    segment gets a gap sized to the mark's own text, so the label sits in a
    notch rather than on top of a solid line."""
    options = config.cable
    routed = route_selected_points(points, selected_numbers)
    segments = list(zip(routed.main, routed.main[1:]))
    mark_indices = set(_cable_mark_indices(len(segments), options.frequency)) if segments else set()
    gap_length = _cable_mark_gap_length(options)

    commands = []
    for index, segment in enumerate(segments):
        start, end = segment
        if index in mark_indices:
            commands.extend(_gapped_segment_line_commands(start, end, gap_length, layer))
            commands.append(_cable_mark_command(segment, options, layer))
        else:
            commands.append(AddLineCommand((start.x, start.y, start.h), (end.x, end.y, end.h), layer))
    commands.extend(_box_line_commands(routed.boxes, layer))
    commands.extend(_wedge_line_commands(routed.wedges, layer))
    return CompositeCommand(commands)


# Rough estimate of a DXF font character's width relative to its height —
# used only to size the notch cut into the cable to roughly match the
# mark's own text, not for any precise text-layout purpose.
_CABLE_MARK_CHAR_WIDTH_RATIO = 0.7
# Extra clearance around the estimated text width, in font-size units.
_CABLE_MARK_GAP_PADDING = 0.5


def _cable_mark_gap_length(options: CableOptions) -> float:
    text_width = len(options.marks_text) * options.font_size * _CABLE_MARK_CHAR_WIDTH_RATIO
    return text_width + options.font_size * _CABLE_MARK_GAP_PADDING


def _gapped_segment_line_commands(start: Point, end: Point, gap_length: float, layer: str) -> List[AddLineCommand]:
    """The segment start->end, split into two LINE entities with a gap
    centred on its midpoint — capped at 80% of the segment's own length so
    a short segment or a long mark never crosses the two halves over."""
    length = math.hypot(end.x - start.x, end.y - start.y)
    if length <= 0:
        return [AddLineCommand((start.x, start.y, start.h), (end.x, end.y, end.h), layer)]
    half_gap = min(gap_length, length * 0.8) / 2.0
    ux, uy = (end.x - start.x) / length, (end.y - start.y) / length
    mid_x, mid_y, mid_h = (start.x + end.x) / 2.0, (start.y + end.y) / 2.0, (start.h + end.h) / 2.0
    gap_start = (mid_x - ux * half_gap, mid_y - uy * half_gap, mid_h)
    gap_end = (mid_x + ux * half_gap, mid_y + uy * half_gap, mid_h)
    return [
        AddLineCommand((start.x, start.y, start.h), gap_start, layer),
        AddLineCommand(gap_end, (end.x, end.y, end.h), layer),
    ]


def _cable_mark_indices(segment_count: int, frequency: int) -> List[int]:
    """Segment indices to mark: the centre segment first, then alternating
    outward by `frequency` segments at a time until both directions run out
    of bounds."""
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
    """Resolves the draw-mode builder registered for `draw_mode`."""
    try:
        return _BUILDERS[draw_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported draw mode: {draw_mode!r}") from exc
