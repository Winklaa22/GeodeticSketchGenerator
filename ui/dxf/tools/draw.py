from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from ezdxf.math import fit_points_to_cad_cv
from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand, AddTextCommand
from core.commands.multileader import AddMultileaderCommand
from core.dxf_document import DXFDocument
from core.multileader import (
    MultileaderSpec,
    MultileaderStyle,
    apply_style,
    arrow_points,
    constrain_angle,
    leader_points,
    spline_fit_points,
)
from ui.dxf.tools.base import (
    ToolSession,
    add_preview_item,
    offset_segment_perpendicular,
    parse_coordinate,
    point_distance,
    preview_pen,
)
from ui.i18n import tr


class PointToolSession(ToolSession):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_point")
        self._point: Optional[Tuple[float, float]] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        self._point = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=None)
        if coord is None:
            return tr("common.point_xy_format", value=text)
        self._point = coord
        return None

    def is_done(self) -> bool:
        return self._point is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._point is not None
        return AddPointCommand(self._point, doc.active_layer)


_DEFAULT_TEXT_HEIGHT = 0.6
_PREVIEW_SPLINE_SEGMENTS = 32
_FILLED_ARROWS = {"closed", "datum_triangle_filled"}
_TRIANGLE_ARROWS = {"closed", "closed_blank", "closed_outline", "datum_triangle", "datum_triangle_filled"}
_OPEN_ARROWS = {"open", "open_30", "right_angle"}
_TICK_ARROWS = {"oblique", "architectural_tick"}
_BOX_ARROWS = {"box", "box_blank"}
_SMALL_DOTS = {"dot_small", "dot_small_blank"}


def leader_curve(spec: MultileaderSpec) -> List[Tuple[float, float]]:
    route = list(leader_points(spec))
    if spec.line_type != "spline":
        return route
    fit_points = spline_fit_points(spec)
    if len(set(fit_points)) < 3:
        return route
    curve = fit_points_to_cad_cv(fit_points)
    return [(vertex.x, vertex.y) for vertex in curve.approximate(_PREVIEW_SPLINE_SEGMENTS)]


def _add_preview(scene: qw.QGraphicsScene, item: qw.QGraphicsItem, sink: List[qw.QGraphicsItem]) -> None:
    item.setPen(preview_pen())
    add_preview_item(scene, item)
    sink.append(item)


def add_polyline_preview(
    scene: qw.QGraphicsScene, points: List[Tuple[float, float]], sink: List[qw.QGraphicsItem]
) -> None:
    path = qg.QPainterPath(qc.QPointF(*points[0]))
    for vertex in points[1:]:
        path.lineTo(qc.QPointF(*vertex))
    _add_preview(scene, qw.QGraphicsPathItem(path), sink)


def _add_polygon_preview(
    scene: qw.QGraphicsScene, points: List[Tuple[float, float]], filled: bool, sink: List[qw.QGraphicsItem]
) -> None:
    item = qw.QGraphicsPolygonItem(qg.QPolygonF([qc.QPointF(*point) for point in points]))
    if filled:
        item.setBrush(qg.QBrush(preview_pen().color()))
    _add_preview(scene, item, sink)


def add_leader_preview(
    scene: qw.QGraphicsScene, spec: MultileaderSpec, sink: List[qw.QGraphicsItem]
) -> None:
    add_polyline_preview(scene, leader_curve(spec), sink)
    arrowhead = spec.arrowhead
    if arrowhead == "none" and not spec.arrow_block:
        return
    tip, left, right = arrow_points(spec)
    if arrowhead in _TRIANGLE_ARROWS:
        _add_polygon_preview(scene, [tip, left, right], arrowhead in _FILLED_ARROWS, sink)
        return
    if arrowhead in _OPEN_ARROWS:
        add_polyline_preview(scene, [left, tip, right], sink)
        return
    base = ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    half = math.hypot(left[0] - right[0], left[1] - right[1]) / 2.0
    angle = math.atan2(base[1] - tip[1], base[0] - tip[0])
    px, py = -math.sin(angle) * half, math.cos(angle) * half
    if arrowhead in _TICK_ARROWS:
        add_polyline_preview(scene, [(tip[0] - px - (base[0] - tip[0]) / 2, tip[1] - py - (base[1] - tip[1]) / 2), (tip[0] + px + (base[0] - tip[0]) / 2, tip[1] + py + (base[1] - tip[1]) / 2)], sink)
        return
    if arrowhead in _BOX_ARROWS:
        corners = [(tip[0] + px, tip[1] + py), (tip[0] - px, tip[1] - py), (base[0] - px, base[1] - py), (base[0] + px, base[1] + py)]
        _add_polygon_preview(scene, corners, arrowhead == "box", sink)
        return
    radius = spec.effective_arrow_size * (0.2 if arrowhead in _SMALL_DOTS else 0.5)
    item = qw.QGraphicsEllipseItem(tip[0] - radius, tip[1] - radius, radius * 2, radius * 2)
    if arrowhead == "dot":
        item.setBrush(qg.QBrush(preview_pen().color()))
    _add_preview(scene, item, sink)


@dataclass(frozen=True)
class MTextValues:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    alignment: str = "auto"


class MultileaderToolSession(ToolSession):

    def __init__(
        self,
        height: float = _DEFAULT_TEXT_HEIGHT,
        line_type: Optional[str] = None,
        arrowhead: Optional[str] = None,
        landing_enabled: Optional[bool] = None,
        attachment: Optional[str] = None,
        style: Optional[MultileaderStyle] = None,
        annotation_scale: float = 1.0,
        direction: Optional[str] = None,
        text_frame: Optional[bool] = None,
    ) -> None:
        super().__init__()
        self.prompt = tr("tool.multileader_tip")
        base = MultileaderSpec(tip=(0.0, 0.0), landing=None, text_position=(0.0, 0.0), text="", height=height, gap=height * 0.3)
        self._first_angle = 0
        if style is not None:
            base = apply_style(base, style)
            self._first_angle = style.first_angle
            if style.annotative:
                base = replace(base, scale=annotation_scale)
        overrides = {
            key: value
            for key, value in (
                ("line_type", line_type),
                ("arrowhead", arrowhead),
                ("attachment", attachment),
                ("direction", direction),
                ("text_frame", text_frame),
            )
            if value is not None
        }
        self._base = replace(base, **overrides)
        if landing_enabled is None:
            landing_enabled = style.landing_enabled if style is not None else True
        self._landing_enabled = landing_enabled and self._base.direction == "horizontal"
        self._tip: Optional[Tuple[float, float]] = None
        self._landing: Optional[Tuple[float, float]] = None
        self._text_position: Optional[Tuple[float, float]] = None
        self._text: Optional[MTextValues] = None
        self._preview_items: List[qw.QGraphicsItem] = []

    @property
    def wants_text_editor(self) -> bool:
        return self._text_position is not None and self._text is None

    @property
    def text_defaults(self) -> MTextValues:
        return MTextValues(
            "",
            self._base.bold,
            self._base.italic,
            self._base.underline,
            self._base.alignment,
        )

    def _fixed_landing(self) -> bool:
        return self._landing_enabled and self._base.landing_length > 0.0

    def _constrained(self, point: Tuple[float, float]) -> Tuple[float, float]:
        if self._tip is None:
            return point
        return constrain_angle(self._tip, point, self._first_angle)

    def _text_after_landing(self, landing: Tuple[float, float]) -> Tuple[float, float]:
        assert self._tip is not None
        sign = 1.0 if landing[0] >= self._tip[0] else -1.0
        return landing[0] + sign * self._base.landing_length * self._base.scale, landing[1]

    def _spec_for(
        self,
        landing: Optional[Tuple[float, float]],
        text_position: Tuple[float, float],
        text: Optional[MTextValues] = None,
    ) -> MultileaderSpec:
        assert self._tip is not None
        values = text or MTextValues("")
        landing_enabled = self._landing_enabled and landing is not None
        if landing_enabled:
            text_position = (text_position[0], landing[1])
        return replace(
            self._base,
            tip=self._tip,
            landing=landing if landing_enabled else None,
            text_position=text_position,
            landing_enabled=landing_enabled,
            landing_length=0.0,
            text=values.text,
            bold=values.bold if text else self._base.bold,
            italic=values.italic if text else self._base.italic,
            underline=values.underline if text else self._base.underline,
            alignment=values.alignment if text else self._base.alignment,
        ).normalized()

    def _advance_to_text_position(self) -> None:
        self.prompt = tr("tool.multileader_text_position")

    def _place_landing(self, point: Tuple[float, float]) -> None:
        self._landing = self._constrained(point)
        if self._fixed_landing():
            self._text_position = self._text_after_landing(self._landing)
            self.prompt = tr("tool.enter_text")
            return
        self._advance_to_text_position()

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._tip is None:
            self._tip = point
            if self._landing_enabled:
                self.prompt = tr("tool.multileader_landing")
            else:
                self._advance_to_text_position()
            return
        if self._landing_enabled and self._landing is None:
            self._place_landing(point)
            return
        if self._text_position is None:
            self._text_position = point if self._landing_enabled else self._constrained(point)
            self.prompt = tr("tool.enter_text")

    def on_text(self, text: str) -> Optional[str]:
        value = text.strip()
        if self._tip is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self.on_click(coord)
            return None
        if self._landing_enabled and self._landing is None:
            if value.upper() in {"N", "NO", "NOLANDING"}:
                self._landing_enabled = False
                self._advance_to_text_position()
                return None
            coord = parse_coordinate(text, last_point=self._tip)
            if coord is None:
                return tr("common.point_xy_or_rel_format", value=text)
            self.on_click(coord)
            return None
        if self._text_position is None:
            coord = parse_coordinate(text, last_point=self._landing or self._tip)
            if coord is None:
                return tr("common.point_xy_or_rel_format", value=text)
            self.on_click(coord)
            return None
        if not value:
            return tr("tool.text_empty")
        defaults = self.text_defaults
        self._text = replace(defaults, text=text.replace("\\P", "\n"))
        return None

    def on_mtext(self, values: MTextValues) -> Optional[str]:
        if self._text_position is None:
            return None
        if not values.text.strip():
            return tr("tool.text_empty")
        self._text = values
        return None

    def _stage_spec(self, point: Tuple[float, float]) -> Optional[MultileaderSpec]:
        if self._tip is None:
            return None
        if self._landing_enabled and self._landing is None:
            landing = self._constrained(point)
            if self._fixed_landing():
                return self._spec_for(landing, self._text_after_landing(landing))
            return replace(self._spec_for(None, landing), landing_enabled=False).normalized()
        if self._text_position is not None:
            return self._spec_for(self._landing, self._text_position)
        return self._spec_for(self._landing, point if self._landing_enabled else self._constrained(point))

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._tip is None or self._text is not None:
            return
        spec = self._stage_spec(point)
        if spec is None:
            return
        self._reset_preview(scene)
        add_leader_preview(scene, spec, self._preview_items)

    def _reset_preview(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def is_done(self) -> bool:
        return self._text_position is not None and self._text is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._text_position is not None and self._text is not None
        spec = self._spec_for(self._landing, self._text_position, self._text)
        return AddMultileaderCommand(replace(spec, layer=doc.active_layer))

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)


class TextToolSession(ToolSession):

    def __init__(self, height: float = _DEFAULT_TEXT_HEIGHT) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_text_point")
        self._insert: Optional[Tuple[float, float]] = None
        self._text: Optional[str] = None
        self._height = height

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._insert is None:
            self._insert = point
            self.prompt = tr("tool.enter_text")

    def on_text(self, text: str) -> Optional[str]:
        if self._insert is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._insert = coord
            self.prompt = tr("tool.enter_text")
            return None
        if not text.strip():
            return tr("tool.text_empty")
        self._text = text
        return None

    def is_done(self) -> bool:
        return self._insert is not None and self._text is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._insert is not None and self._text is not None
        return AddTextCommand(self._text, self._insert, self._height, doc.active_layer)


class LineToolSession(ToolSession):

    def __init__(self, start: Optional[Tuple[float, float]] = None) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_next_point") if start is not None else tr("tool.specify_first_point")
        self._start: Optional[Tuple[float, float]] = start
        self._end: Optional[Tuple[float, float]] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._start is None:
            self._start = point
            self.prompt = tr("tool.specify_next_point")
        else:
            self._end = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=self._start)
        if coord is None:
            return tr("common.point_xy_or_rel_format", value=text)
        if self._start is None:
            self._start = coord
            self.prompt = tr("tool.specify_next_point")
        else:
            self._end = coord
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._start is None or self._end is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(self._start[0], self._start[1], point[0], point[1])

    def is_done(self) -> bool:
        return self._start is not None and self._end is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._start is not None and self._end is not None
        return AddLineCommand(self._start, self._end, doc.active_layer)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None

    def continuation(self) -> "LineToolSession":
        assert self._end is not None
        return LineToolSession(start=self._end)


class CircleToolSession(ToolSession):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_center_point")
        self._center: Optional[Tuple[float, float]] = None
        self._radius: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsEllipseItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._center is None:
            self._center = point
            self.prompt = tr("tool.specify_radius_or_point")
        else:
            self._radius = point_distance(self._center, point)

    def on_text(self, text: str) -> Optional[str]:
        if self._center is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._center = coord
            self.prompt = tr("tool.specify_radius_or_point")
            return None
        try:
            radius = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._center)
            if coord is None:
                return tr("tool.radius_or_point_numeric", value=text)
            radius = point_distance(self._center, coord)
        if radius <= 0:
            return tr("common.radius_positive")
        self._radius = radius
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._center is None or self._radius is not None:
            return
        radius = point_distance(self._center, point)
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsEllipseItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        cx, cy = self._center
        self._preview_item.setRect(cx - radius, cy - radius, radius * 2, radius * 2)

    def is_done(self) -> bool:
        return self._center is not None and self._radius is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._center is not None and self._radius is not None
        return AddCircleCommand(self._center, self._radius, doc.active_layer)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None


class PipeToolSession(ToolSession):

    def __init__(
        self, start: Optional[Tuple[float, float]] = None, width: Optional[float] = None
    ) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_next_point") if start is not None else tr("tool.specify_first_point")
        self._start: Optional[Tuple[float, float]] = start
        self._end: Optional[Tuple[float, float]] = None
        self._width: Optional[float] = width
        self._preview_items: List[qw.QGraphicsLineItem] = []

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._start is None:
            self._start = point
            self.prompt = tr("tool.specify_next_point")
        elif self._end is None:
            self._end = point
            if self._width is None:
                self.prompt = tr("tool.specify_pipe_width_or_point")
        elif self._width is None:
            width = point_distance(self._end, point)
            if width > 0:
                self._width = width

    def on_text(self, text: str) -> Optional[str]:
        if self._start is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._start = coord
            self.prompt = tr("tool.specify_next_point")
            return None
        if self._end is None:
            coord = parse_coordinate(text, last_point=self._start)
            if coord is None:
                return tr("common.point_xy_or_rel_format", value=text)
            self._end = coord
            if self._width is None:
                self.prompt = tr("tool.specify_pipe_width_or_point")
            return None
        try:
            width = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._end)
            if coord is None:
                return tr("tool.width_or_point_numeric", value=text)
            width = point_distance(self._end, coord)
        if width <= 0:
            return tr("common.width_positive")
        self._width = width
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._start is None:
            return
        if self._end is None:
            self._set_preview_segments(scene, [(self._start, point)])
            return
        if self._width is not None:
            return
        width = point_distance(self._end, point)
        if width <= 0:
            self._set_preview_segments(scene, [])
            return
        half = width / 2.0
        self._set_preview_segments(
            scene,
            [
                offset_segment_perpendicular(self._start, self._end, half),
                offset_segment_perpendicular(self._start, self._end, -half),
            ],
        )

    def _set_preview_segments(
        self, scene: qw.QGraphicsScene, segments: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    ) -> None:
        while len(self._preview_items) < len(segments):
            item = qw.QGraphicsLineItem()
            item.setPen(preview_pen())
            add_preview_item(scene, item)
            self._preview_items.append(item)
        while len(self._preview_items) > len(segments):
            scene.removeItem(self._preview_items.pop())
        for item, (a, b) in zip(self._preview_items, segments):
            item.setLine(a[0], a[1], b[0], b[1])

    def is_done(self) -> bool:
        return self._start is not None and self._end is not None and self._width is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._start is not None and self._end is not None and self._width is not None
        layer = doc.active_layer
        half = self._width / 2.0
        line_a = offset_segment_perpendicular(self._start, self._end, half)
        line_b = offset_segment_perpendicular(self._start, self._end, -half)
        return CompositeCommand(
            [AddLineCommand(line_a[0], line_a[1], layer), AddLineCommand(line_b[0], line_b[1], layer)]
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def continuation(self) -> "PipeToolSession":
        assert self._end is not None and self._width is not None
        return PipeToolSession(start=self._end, width=self._width)
