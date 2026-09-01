from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from ezdxf.addons.drawing.backend import Backend, BkPath2d, BkPoints2d, ImageData
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing.properties import BackendProperties
from ezdxf.addons.drawing.type_hints import Color
from ezdxf.math import Vec2
from ezdxf.path import Command

from core.plot import StrokeStyle
from ui.dxf.items import HANDLE_ROLE, PointItem


@lru_cache(maxsize=512)
def qcolor_from(color: Color) -> qg.QColor:
    if len(color) == 7:
        return qg.QColor(color)
    if len(color) == 9:
        return qg.QColor(f"#{color[7:9]}{color[1:7]}")
    raise ValueError(f"unsupported color format: {color!r}")


def to_qpainter_path(paths: Iterable[BkPath2d]) -> qg.QPainterPath:
    qpath = qg.QPainterPath()
    for path in paths:
        points = [qc.QPointF(v.x, v.y) for v in path.vertices()]
        qpath.moveTo(points[0])
        index = 1
        for cmd in path.command_codes():
            if cmd == Command.LINE_TO:
                qpath.lineTo(points[index])
                index += 1
            elif cmd == Command.CURVE3_TO:
                qpath.quadTo(points[index], points[index + 1])
                index += 2
            elif cmd == Command.CURVE4_TO:
                qpath.cubicTo(points[index], points[index + 1], points[index + 2])
                index += 3
            elif cmd == Command.MOVE_TO:
                qpath.moveTo(points[index])
                index += 1
    return qpath


class QtSceneBackend(Backend):

    def __init__(
        self, scene: qw.QGraphicsScene, stroke: Optional[StrokeStyle] = None
    ) -> None:
        super().__init__()
        self._scene = scene
        self._stroke = stroke
        self._no_line = qg.QPen(qc.Qt.PenStyle.NoPen)
        self._no_fill = qg.QBrush(qc.Qt.BrushStyle.NoBrush)

    def configure(self, config: Configuration) -> None:
        if config.min_lineweight is None:
            config = config.with_changes(min_lineweight=0.24)
        super().configure(config)

    def _add(self, item: qw.QGraphicsItem, handle: str) -> None:
        item.setData(HANDLE_ROLE, handle)
        self._scene.addItem(item)

    def _pen(self, properties: BackendProperties) -> qg.QPen:
        pen = qg.QPen(qcolor_from(properties.color))
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        if self._stroke is None:
            pen.setWidthF(properties.lineweight / 0.3527 * self.config.lineweight_scaling)
            pen.setCosmetic(True)
        else:
            pen.setWidthF(self._stroke.pen_width(properties.lineweight))
            pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
        return pen

    def _fill_brush(self, color: Color) -> qg.QBrush:
        return qg.QBrush(qcolor_from(color), qc.Qt.BrushStyle.SolidPattern)

    def set_background(self, color: Color) -> None:
        if self._stroke is not None:
            return
        self._scene.setBackgroundBrush(qg.QBrush(qcolor_from(color)))

    def draw_point(self, pos: Vec2, properties: BackendProperties) -> None:
        radius = self._stroke.point_radius() if self._stroke is not None else None
        item = PointItem(pos.x, pos.y, self._fill_brush(properties.color), radius)
        self._add(item, properties.handle)

    def draw_line(self, start: Vec2, end: Vec2, properties: BackendProperties) -> None:
        if start.isclose(end):
            self.draw_point(start, properties)
            return
        item = qw.QGraphicsLineItem(start.x, start.y, end.x, end.y)
        item.setPen(self._pen(properties))
        self._add(item, properties.handle)

    def draw_solid_lines(
        self, lines: Iterable[Tuple[Vec2, Vec2]], properties: BackendProperties
    ) -> None:
        pen = self._pen(properties)
        for start, end in lines:
            if start.isclose(end):
                self.draw_point(start, properties)
                continue
            item = qw.QGraphicsLineItem(start.x, start.y, end.x, end.y)
            item.setPen(pen)
            self._add(item, properties.handle)

    def draw_path(self, path: BkPath2d, properties: BackendProperties) -> None:
        if len(path) == 0:
            return
        item = qw.QGraphicsPathItem(to_qpainter_path([path]))
        item.setPen(self._pen(properties))
        item.setBrush(self._no_fill)
        self._add(item, properties.handle)

    def draw_filled_paths(
        self, paths: Iterable[BkPath2d], properties: BackendProperties
    ) -> None:
        paths = list(paths)
        if not paths:
            return
        item = qw.QGraphicsPathItem(to_qpainter_path(paths))
        item.setPen(self._no_line if self._stroke is not None else self._pen(properties))
        item.setBrush(self._fill_brush(properties.color))
        self._add(item, properties.handle)

    def draw_filled_polygon(
        self, points: BkPoints2d, properties: BackendProperties
    ) -> None:
        polygon = qg.QPolygonF([qc.QPointF(p.x, p.y) for p in points.vertices()])
        item = qw.QGraphicsPolygonItem(polygon)
        item.setPen(self._no_line)
        item.setBrush(self._fill_brush(properties.color))
        self._add(item, properties.handle)

    def draw_image(self, image_data: ImageData, properties: BackendProperties) -> None:
        return

    def clear(self) -> None:
        self._scene.clear()

    def finalize(self) -> None:
        super().finalize()
        self._scene.setSceneRect(self._scene.itemsBoundingRect())

