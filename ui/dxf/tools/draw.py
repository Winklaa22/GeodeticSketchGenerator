from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand, AddTextCommand
from core.dxf_document import DXFDocument
from ui.dxf.tools.base import (
    ToolSession,
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
            scene.addItem(self._preview_item)
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
            scene.addItem(self._preview_item)
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
            scene.addItem(item)
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
