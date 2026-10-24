from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from core.cable_annotation import CableSlot, SlotKind, plan_cable_slots
from core.commands.base import Command
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
    compute_direction_angle,
    iter_point_directions,
    offset_segment_perpendicular,
    snap_small_rotation,
)
from core.label_placement import LabelRequest, Obstacles, label_extent, solve_label_positions
from core.patterns import route_selected_points
from core.route_graph import build_cable_chains, build_route_graph
from models.point import Point

Point2D = Tuple[float, float]

CABLE_LABEL_GAP_FACTOR = 0.5
CABLE_LABEL_MIN_GAP_FACTOR = 7.0


@dataclass(frozen=True)
class _PendingLabel:
    request: LabelRequest
    render: Callable[[Point2D], AddTextCommand]


def _route_segments(
    points: Dict[int, Point], selected_numbers: List[int]
) -> List[Tuple[Point2D, Point2D]]:
    routed = route_selected_points(points, selected_numbers)
    segments = [((a.x, a.y), (b.x, b.y)) for a, b in zip(routed.main, routed.main[1:])]
    for box in routed.boxes:
        size = len(box)
        for k in range(size):
            a, b = box[k], box[(k + 1) % size]
            segments.append(((a.x, a.y), (b.x, b.y)))
    for entry, wing_1, wing_2 in routed.wedges:
        segments.append(((entry.x, entry.y), (wing_1.x, wing_1.y)))
        segments.append(((entry.x, entry.y), (wing_2.x, wing_2.y)))
    return segments


def _pooled_selection(configs: List[GenerationConfig]) -> List[int]:
    """Every point any of these modes draws, in order and without repeats."""
    return list(dict.fromkeys(number for config in configs for number in config.selected_numbers))


def _build_obstacles(points: Dict[int, Point], selected_numbers: List[int], marker_radius: float) -> Obstacles:
    markers = [(points[n].x, points[n].y, marker_radius) for n in selected_numbers if n in points]
    return Obstacles(markers=markers, segments=_route_segments(points, selected_numbers))


def _cabinet_numbers(points: Dict[int, Point], selected_numbers: List[int]) -> Set[int]:
    routed = route_selected_points(points, selected_numbers)
    number_by_id = {id(p): n for n, p in points.items()}
    clusters = [list(box) for box in routed.boxes]

    numbers: Set[int] = set()
    for cluster in clusters:
        cluster_numbers = {number_by_id[id(p)] for p in cluster}
        centroid_x = sum(p.x for p in cluster) / len(cluster)
        centroid_y = sum(p.y for p in cluster) / len(cluster)
        cluster_radius = max(math.hypot(p.x - centroid_x, p.y - centroid_y) for p in cluster)
        for point in routed.main:
            number = number_by_id[id(point)]
            if number in cluster_numbers:
                continue
            if math.hypot(point.x - centroid_x, point.y - centroid_y) <= cluster_radius:
                cluster_numbers.add(number)
        numbers.update(cluster_numbers)
    return numbers


def _perpendicular_prefer(start: Point, end: Point, flip: bool) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    if dx == 0.0 and dy == 0.0:
        return 0.0
    angle = math.atan2(dx, -dy)
    return angle + math.pi if flip else angle


def _finalize(
    points: Dict[int, Point],
    selected_numbers: List[int],
    config: GenerationConfig,
    structural: List[Command],
    pending: List[_PendingLabel],
) -> CompositeCommand:
    marker_radius = max(config.points.diameter / 2.0, 0.0)
    obstacles = _build_obstacles(points, selected_numbers, marker_radius)
    positions, _collisions = solve_label_positions([p.request for p in pending], obstacles, marker_radius)
    labels = [p.render(positions[p.request.key]) for p in pending]
    return CompositeCommand(structural + labels)


def _stage_points(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    options = config.points
    radius = max(options.diameter / 2.0, 0.0)
    directions = list(iter_point_directions(points, selected_numbers))
    structural: List[Command] = [
        AddCircleCommand((d.point.x, d.point.y, d.point.h), radius, layer) for d in directions
    ]
    pending: List[_PendingLabel] = []
    if options.numbers_enabled:
        cabinet_numbers = (
            _cabinet_numbers(points, selected_numbers) if options.cabinet_font_size_enabled else set()
        )
        for direction in directions:
            point = direction.point
            number = direction.number
            size = options.cabinet_font_size if number in cabinet_numbers else options.font_size
            key = ("points", number)
            request = LabelRequest(
                key=key, anchor=(point.x, point.y), text=str(number), font_size=size, prefer=None
            )

            def render(
                pos: Point2D, point: Point = point, number: int = number, size: float = size, layer: str = layer,
                font_id: str = config.font_id, font_italic: bool = config.font_italic,
                font_lineweight_mm: Optional[float] = config.font_lineweight_mm,
            ) -> AddTextCommand:
                insert = (pos[0], pos[1], point.h)
                return AddTextCommand(
                    str(number), insert, size, layer, halign="center", valign="middle", font_id=font_id,
                    italic=font_italic, lineweight_mm=font_lineweight_mm,
                )

            pending.append(_PendingLabel(request, render))
    return structural, pending


def build_points_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    structural, pending = _stage_points(points, selected_numbers, config, layer)
    return _finalize(points, selected_numbers, config, structural, pending)


def _selected_points(points: Dict[int, Point], selected_numbers: List[int]) -> Dict[int, Point]:
    return {n: points[n] for n in selected_numbers if n in points}


def _outline_line_commands(outlines: List[Tuple[int, ...]], points: Dict[int, Point], layer: str) -> List[AddLineCommand]:
    commands = []
    for outline in outlines:
        size = len(outline)
        for k in range(size):
            a, b = points[outline[k]], points[outline[(k + 1) % size]]
            commands.append(AddLineCommand((a.x, a.y, a.h), (b.x, b.y, b.h), layer))
    return commands


def _outline_polyline2d_commands(
    outlines: List[Tuple[int, ...]], points: Dict[int, Point], layer: str
) -> List[AddPolyline2DCommand]:
    return [
        AddPolyline2DCommand([(points[n].x, points[n].y) for n in outline], layer, closed=True) for outline in outlines
    ]


def _outline_polyline3d_commands(
    outlines: List[Tuple[int, ...]], points: Dict[int, Point], layer: str
) -> List[AddPolyline3DCommand]:
    return [
        AddPolyline3DCommand([(points[n].x, points[n].y, points[n].h) for n in outline], layer, closed=True)
        for outline in outlines
    ]


def build_lines_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    selected = _selected_points(points, selected_numbers)
    graph = build_route_graph(selected, config.quantum)
    commands = [
        AddLineCommand(
            (selected[a].x, selected[a].y, selected[a].h), (selected[b].x, selected[b].y, selected[b].h), layer
        )
        for a, b in graph.edges
    ]
    commands.extend(_outline_line_commands(graph.outlines, selected, layer))
    return CompositeCommand(commands)


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
    selected = _selected_points(points, selected_numbers)
    graph = build_route_graph(selected, config.quantum)
    chains = build_cable_chains(graph.edges, graph.junctions)
    commands = [
        AddPolyline2DCommand([(selected[n].x, selected[n].y) for n in chain], layer) for chain in chains
    ]
    commands.extend(_outline_polyline2d_commands(graph.outlines, selected, layer))
    return CompositeCommand(commands)


def build_poly3d_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    selected = _selected_points(points, selected_numbers)
    graph = build_route_graph(selected, config.quantum)
    chains = build_cable_chains(graph.edges, graph.junctions)
    commands = [
        AddPolyline3DCommand([(selected[n].x, selected[n].y, selected[n].h) for n in chain], layer)
        for chain in chains
    ]
    commands.extend(_outline_polyline3d_commands(graph.outlines, selected, layer))
    return CompositeCommand(commands)


def _height_text(h: float) -> str:
    return str(math.ceil(h * 10) / 10)


def _plan_cable_slots(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig
) -> List[CableSlot]:
    selected = _selected_points(points, selected_numbers)
    if len(selected) < 2:
        return []
    graph = build_route_graph(selected, config.quantum)
    chains = [[selected[n] for n in chain] for chain in build_cable_chains(graph.edges, graph.junctions)]
    font_size = max(config.cable.font_size, config.heights.font_size)
    tallest = max(selected.values(), key=lambda p: abs(p.h))
    label_width = max(
        label_extent(config.cable.font_size, config.cable.marks_text)[0],
        label_extent(config.heights.font_size, _height_text(tallest.h))[0],
    )
    marker_radius = max(config.points.diameter / 2.0, 0.0)
    clearance = marker_radius + CABLE_LABEL_GAP_FACTOR * font_size
    spacing = config.cable.spacing * font_size
    return plan_cable_slots(chains, spacing, label_width, clearance, CABLE_LABEL_MIN_GAP_FACTOR * font_size)


def _stage_cable_slots(
    points: Dict[int, Point],
    selected_numbers: List[int],
    config: GenerationConfig,
    layer: str,
    kind: SlotKind,
    key_prefix: str,
    font_size: float,
    text_of: Callable[[CableSlot], str],
) -> Tuple[List[Command], List[_PendingLabel]]:
    pending: List[_PendingLabel] = []
    slots = [slot for slot in _plan_cable_slots(points, selected_numbers, config) if slot.kind is kind]
    for index, slot in enumerate(slots):
        text = text_of(slot)
        anchor = (slot.x, slot.y)
        request = LabelRequest(
            key=(key_prefix, config.run, index), anchor=anchor, text=text, font_size=font_size, prefer=None, fixed=anchor
        )

        def render(
            pos: Point2D, text: str = text, size: float = font_size, layer: str = layer,
            rotation: float = slot.rotation, z: float = slot.h, font_id: str = config.font_id,
            font_italic: bool = config.font_italic, font_lineweight_mm: Optional[float] = config.font_lineweight_mm,
        ) -> AddTextCommand:
            insert = (pos[0], pos[1], z)
            return AddTextCommand(
                text, insert, size, layer, rotation, halign="center", valign="middle", font_id=font_id,
                italic=font_italic, lineweight_mm=font_lineweight_mm,
            )

        pending.append(_PendingLabel(request, render))
    return [], pending


def _stage_heights(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    return _stage_cable_slots(
        points, selected_numbers, config, layer, SlotKind.HEIGHT, "heights", config.heights.font_size,
        lambda slot: _height_text(slot.h),
    )


def build_heights_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    structural, pending = _stage_heights(points, selected_numbers, config, layer)
    return _finalize(points, selected_numbers, config, structural, pending)


def _stage_cable_marks(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    return _stage_cable_slots(
        points, selected_numbers, config, layer, SlotKind.MARK, "cable_marks", config.cable.font_size,
        lambda _slot: config.cable.marks_text,
    )


def build_cable_marks_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    structural, pending = _stage_cable_marks(points, selected_numbers, config, layer)
    return _finalize(points, selected_numbers, config, structural, pending)


def _stage_measurements(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    options = config.measurements
    routed = route_selected_points(points, selected_numbers)
    segments = list(zip(routed.main, routed.main[1:]))
    for entry, wing_1, wing_2 in routed.wedges:
        segments.append((entry, wing_1))
        segments.append((entry, wing_2))

    pending: List[_PendingLabel] = []
    for index, (start, end) in enumerate(segments):
        distance = math.hypot(end.x - start.x, end.y - start.y)
        if distance <= 0:
            continue
        angle_deg = compute_direction_angle(start, end)
        rotation = snap_small_rotation(angle_deg, round(angle_deg, 1))
        mid_x, mid_y = (start.x + end.x) / 2.0, (start.y + end.y) / 2.0
        prefer = _perpendicular_prefer(start, end, flip=True)
        text = f"-{distance:.2f}-"
        z = (start.h + end.h) / 2.0
        key = ("measurements", config.run, index)
        request = LabelRequest(
            key=key, anchor=(mid_x, mid_y), text=text, font_size=options.font_size, prefer=prefer
        )

        def render(
            pos: Point2D, text: str = text, size: float = options.font_size, layer: str = layer,
            rotation: float = rotation, z: float = z, font_id: str = config.font_id,
            font_italic: bool = config.font_italic, font_lineweight_mm: Optional[float] = config.font_lineweight_mm,
        ) -> AddTextCommand:
            insert = (pos[0], pos[1], z)
            return AddTextCommand(
                text, insert, size, layer, rotation, halign="center", valign="middle", font_id=font_id,
                italic=font_italic, lineweight_mm=font_lineweight_mm,
            )

        pending.append(_PendingLabel(request, render))
    return [], pending


def build_measurements_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    structural, pending = _stage_measurements(points, selected_numbers, config, layer)
    return _finalize(points, selected_numbers, config, structural, pending)


SurveyBuilder = Callable[[Dict[int, Point], List[int], GenerationConfig, str], CompositeCommand]

_BUILDERS: Dict[DrawMode, SurveyBuilder] = {
    DrawMode.POINTS: build_points_command,
    DrawMode.LINES: build_lines_command,
    DrawMode.PLINES: build_plines_command,
    DrawMode.POLY3D: build_poly3d_command,
    DrawMode.HEIGHTS: build_heights_command,
    DrawMode.CABLE_MARKS: build_cable_marks_command,
    DrawMode.PIPE: build_pipe_command,
    DrawMode.MEASUREMENTS: build_measurements_command,
}

_LabelStageBuilder = Callable[
    [Dict[int, Point], List[int], GenerationConfig, str], Tuple[List[Command], List[_PendingLabel]]
]

_LABEL_STAGE_BUILDERS: Dict[DrawMode, _LabelStageBuilder] = {
    DrawMode.POINTS: _stage_points,
    DrawMode.HEIGHTS: _stage_heights,
    DrawMode.CABLE_MARKS: _stage_cable_marks,
    DrawMode.MEASUREMENTS: _stage_measurements,
}


def get_survey_builder(draw_mode: DrawMode) -> SurveyBuilder:
    try:
        return _BUILDERS[draw_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported draw mode: {draw_mode!r}") from exc


def build_survey_commands(
    points: Dict[int, Point],
    configs: List[GenerationConfig],
    layer_names: List[str],
) -> List[CompositeCommand]:
    if not configs:
        return []
    marker_radius = max(configs[0].points.diameter / 2.0, 0.0)
    # Labels have to dodge every point being drawn in this run, not just the ones their
    # own mode selected, so the obstacles are pooled across the modes.
    obstacles = _build_obstacles(points, _pooled_selection(configs), marker_radius)

    per_config: List[Tuple[List[Command], List[_PendingLabel]]] = []
    for config, layer in zip(configs, layer_names):
        selected_numbers = list(config.selected_numbers)
        stage = _LABEL_STAGE_BUILDERS.get(config.draw_mode)
        if stage is not None:
            per_config.append(stage(points, selected_numbers, config, layer))
        else:
            command = get_survey_builder(config.draw_mode)(points, selected_numbers, config, layer)
            per_config.append(([command], []))

    all_requests = [pending.request for _structural, pending_list in per_config for pending in pending_list]
    positions, _collisions = solve_label_positions(all_requests, obstacles, marker_radius)

    results: List[CompositeCommand] = []
    for structural, pending_list in per_config:
        labels = [pending.render(positions[pending.request.key]) for pending in pending_list]
        results.append(CompositeCommand(structural + labels))
    return results
