from __future__ import annotations

from typing import List, Optional, Tuple

from ezdxf.math import fit_points_to_cad_cv
from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand, AddTextCommand
from core.commands.multileader import AddMultileaderCommand
from core.dxf_document import DXFDocument
from core.multileader import MultileaderSpec, arrow_points, leader_points, spline_fit_points
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


def add_leader_preview(
    scene: qw.QGraphicsScene, spec: MultileaderSpec, sink: List[qw.QGraphicsItem]
) -> None:
    """Draws the leader route and its arrowhead, appending every item to ``sink``."""
    add_polyline_preview(scene, leader_curve(spec), sink)
    tip, left, right = arrow_points(spec)
    if spec.arrowhead == "closed":
        polygon = qg.QPolygonF([qc.QPointF(*tip), qc.QPointF(*left), qc.QPointF(*right)])
        item = qw.QGraphicsPolygonItem(polygon)
        item.setBrush(qg.QBrush(preview_pen().color()))
        _add_preview(scene, item, sink)
        return
    if spec.arrowhead == "open":
        add_polyline_preview(scene, [left, tip, right], sink)
        return
    radius = max(spec.height * 0.28, 0.04)
    _add_preview(
        scene, qw.QGraphicsEllipseItem(tip[0] - radius, tip[1] - radius, radius * 2, radius * 2), sink
    )


class MultileaderToolSession(ToolSession):

    def __init__(
        self,
        height: float = _DEFAULT_TEXT_HEIGHT,
        line_type: str = "straight",
        arrowhead: str = "closed",
        landing_enabled: bool = True,
        attachment: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.prompt = tr("tool.multileader_tip")
        self._height = height
        self._line_type = line_type
        self._arrowhead = arrowhead
        self._landing_enabled = landing_enabled
        self._attachment = attachment
        self._tip: Optional[Tuple[float, float]] = None
        self._landing: Optional[Tuple[float, float]] = None
        self._text_position: Optional[Tuple[float, float]] = None
        self._text: Optional[str] = None
        self._preview_items: List[qw.QGraphicsItem] = []

    def _landed_text_position(self, point: Tuple[float, float]) -> Tuple[float, float]:
        if self._landing_enabled and self._landing is not None:
            return point[0], self._landing[1]
        return point

    def _spec(self, text: str = "") -> Optional[MultileaderSpec]:
        return self._spec_for(self._text_position, text)

    def _spec_for(self, text_position: Optional[Tuple[float, float]], text: str = "") -> Optional[MultileaderSpec]:
        if self._tip is None or text_position is None:
            return None
        anchor = self._landing if self._landing_enabled and self._landing is not None else self._tip
        text_position = self._landed_text_position(text_position)
        attachment = self._attachment or ("left" if text_position[0] >= anchor[0] else "right")
        return MultileaderSpec(
            tip=self._tip,
            landing=self._landing,
            text_position=text_position,
            text=text,
            height=self._height,
            line_type=self._line_type,
            arrowhead=self._arrowhead,
            attachment=attachment,
            landing_enabled=self._landing_enabled,
            gap=self._height * 0.3,
        ).normalized()

    def _advance_to_text_position(self) -> None:
        self.prompt = tr("tool.multileader_text_position")

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._tip is None:
            self._tip = point
            if self._landing_enabled:
                self.prompt = tr("tool.multileader_landing")
            else:
                self._advance_to_text_position()
            return
        if self._landing_enabled and self._landing is None:
            self._landing = point
            self._advance_to_text_position()
            return
        if self._text_position is None:
            self._text_position = point
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
            option = value.upper()
            if option in {"N", "NO", "NOLANDING"}:
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
        if not text.strip():
            return tr("tool.text_empty")
        self._text = text
        return None

    def _stage_spec(self, point: Tuple[float, float]) -> Optional[MultileaderSpec]:
        if self._tip is None:
            return None
        if self._landing_enabled and self._landing is None:
            return MultileaderSpec(
                tip=self._tip,
                landing=None,
                text_position=point,
                text="",
                height=self._height,
                line_type=self._line_type,
                arrowhead=self._arrowhead,
                attachment=self._attachment or "left",
                landing_enabled=False,
                gap=0.0,
            ).normalized()
        return self._spec_for(point)

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._tip is None or self._text is not None:
            return
        spec = self._stage_spec(self._text_position if self._text_position is not None else point)
        if spec is None:
            return
        self._reset_preview(scene)
        add_leader_preview(scene, spec, self._preview_items)

    def _reset_preview(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def is_done(self) -> bool:
        return self._spec(self._text or "") is not None and self._text is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        spec = self._spec(self._text or "")
        assert spec is not None and self._text is not None
        return AddMultileaderCommand(
            MultileaderSpec(
                tip=spec.tip,
                landing=spec.landing,
                text_position=spec.text_position,
                text=spec.text,
                height=spec.height,
                line_type=spec.line_type,
                arrowhead=spec.arrowhead,
                attachment=spec.attachment,
                landing_enabled=spec.landing_enabled,
                gap=spec.gap,
                layer=doc.active_layer,
                identifier=spec.identifier,
            )
        )

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
