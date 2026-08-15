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
from core.config import GenerationConfig
from core.draw_modes import DrawMode
from core.geometry import (
    AngleQuadrant,
    PointDirection,
    classify_quadrant,
    iter_point_directions,
    snap_small_rotation,
)
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
    """A chain of LINE entities through consecutive selected points — the
    direct-entity equivalent of chaining multiple points into AutoCAD's LINE
    command, which itself creates one LINE segment per consecutive pair."""
    ordered = _ordered_points(points, selected_numbers)
    commands = [
        AddLineCommand((a.x, a.y, a.h), (b.x, b.y, b.h), layer) for a, b in zip(ordered, ordered[1:])
    ]
    return CompositeCommand(commands)


def build_plines_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    """A single 2D LWPOLYLINE through the selected points (XY only)."""
    ordered = _ordered_points(points, selected_numbers)
    return CompositeCommand([AddPolyline2DCommand([(p.x, p.y) for p in ordered], layer)])


def build_poly3d_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    """A single 3D POLYLINE through the selected points (X, Y, height)."""
    ordered = _ordered_points(points, selected_numbers)
    return CompositeCommand([AddPolyline3DCommand([(p.x, p.y, p.h) for p in ordered], layer)])


def _ordered_points(points: Dict[int, Point], selected_numbers: List[int]) -> List[Point]:
    return [points[n] for n in selected_numbers if n in points]


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
    """A TEXT label (config.cable.marks_text) at the midpoint of every Nth
    selected point's segment to its successor (N = config.cable.frequency)."""
    options = config.cable
    commands = []
    for direction in iter_point_directions(points, selected_numbers):
        if direction.next_point is None:
            continue
        if direction.number % options.frequency != 0:
            continue
        mid_x = (direction.point.x + direction.next_point.x) / 2.0
        mid_y = (direction.point.y + direction.next_point.y) / 2.0
        x_offset, y_offset = _cable_label_offset(direction.angle_deg, options.font_size)
        rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
        insert = (mid_x + x_offset, mid_y + y_offset, direction.point.h)
        commands.append(AddTextCommand(options.marks_text, insert, options.font_size, layer, rotation))
    return CompositeCommand(commands)


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
}


def get_survey_builder(draw_mode: DrawMode) -> SurveyBuilder:
    """Resolves the draw-mode builder registered for `draw_mode`."""
    try:
        return _BUILDERS[draw_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported draw mode: {draw_mode!r}") from exc
