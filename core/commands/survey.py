from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

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
from core.label_placement import LabelRequest, Obstacles, solve_label_positions
from core.patterns import route_selected_points
from core.route_graph import build_cable_chains, build_route_graph
from models.point import Point

Point2D = Tuple[float, float]


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


def _stage_heights(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    options = config.heights
    pending: List[_PendingLabel] = []
    for direction in iter_point_directions(points, selected_numbers):
        if direction.number % options.frequency != 0:
            continue
        point = direction.point
        rotation = snap_small_rotation(direction.angle_deg, direction.rotation)
        rounded_height = math.ceil(point.h * 10) / 10
        text = str(rounded_height)
        key = ("heights", direction.number)
        request = LabelRequest(
            key=key, anchor=(point.x, point.y), text=text, font_size=options.font_size, prefer=None
        )

        def render(
            pos: Point2D, point: Point = point, text: str = text, size: float = options.font_size,
            layer: str = layer, rotation: float = rotation, font_id: str = config.font_id,
            font_italic: bool = config.font_italic, font_lineweight_mm: Optional[float] = config.font_lineweight_mm,
        ) -> AddTextCommand:
            insert = (pos[0], pos[1], point.h)
            return AddTextCommand(
                text, insert, size, layer, rotation, halign="center", valign="middle", font_id=font_id,
                italic=font_italic, lineweight_mm=font_lineweight_mm,
            )

        pending.append(_PendingLabel(request, render))
    return [], pending


def build_heights_command(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> CompositeCommand:
    structural, pending = _stage_heights(points, selected_numbers, config, layer)
    return _finalize(points, selected_numbers, config, structural, pending)


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


def _stage_cable_marks(
    points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig, layer: str
) -> Tuple[List[Command], List[_PendingLabel]]:
    options = config.cable
    routed = route_selected_points(points, selected_numbers)
    segments = list(zip(routed.main, routed.main[1:]))
    mark_indices = _cable_mark_indices(len(segments), options.frequency) if segments else []
    pending: List[_PendingLabel] = []
    for index in mark_indices:
        start, end = segments[index]
        angle_deg = compute_direction_angle(start, end)
        mid_x, mid_y = (start.x + end.x) / 2.0, (start.y + end.y) / 2.0
        rotation = snap_small_rotation(angle_deg, round(angle_deg, 1))
        text = options.marks_text
        z = start.h
        key = ("cable_marks", index)
        request = LabelRequest(
            key=key, anchor=(mid_x, mid_y), text=text, font_size=options.font_size, prefer=None
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
        key = ("measurements", index)
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
    selected_numbers: List[int],
    configs: List[GenerationConfig],
    layer_names: List[str],
) -> List[CompositeCommand]:
    if not configs:
        return []
    marker_radius = max(configs[0].points.diameter / 2.0, 0.0)
    obstacles = _build_obstacles(points, selected_numbers, marker_radius)

    per_config: List[Tuple[List[Command], List[_PendingLabel]]] = []
    for config, layer in zip(configs, layer_names):
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
