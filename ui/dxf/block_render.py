"""Blocks drawn on their own - for the library thumbnails and the insertion preview.

Both go through the same ezdxf front end as the drawing itself, so a block looks the
same in the palette as it will once placed: text, fills and all.
"""
from __future__ import annotations

from typing import List, Tuple

from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration
from ezdxf.document import Drawing
from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from ui.dxf.backend import QtSceneBackend
from ui.dxf.items import PointItem

# One drawn piece of a block, with its base point at the origin, and whether it is filled.
Shape = Tuple[qg.QPainterPath, bool]


def block_shapes(drawing: Drawing, name: str) -> List[Shape]:
    """A block defined in `drawing`, drawn in its own coordinates."""
    scene = qw.QGraphicsScene()
    context = RenderContext(drawing)
    # A block definition is not a layout of its own, so it borrows the modelspace's
    # layout properties - the same ones it is drawn under once inserted there.
    context.set_current_layout(drawing.modelspace())
    frontend = Frontend(context, QtSceneBackend(scene), config=Configuration())
    frontend.parent_stack = []
    block = drawing.blocks[name]
    frontend.draw_entities(block)
    frontend.pipeline.finalize()
    base = block.block.dxf.base_point
    return _shapes(scene, base.x, base.y)


def file_shapes(drawing: Drawing) -> List[Shape]:
    """A block file - its whole modelspace - with its $INSBASE at the origin."""
    scene = qw.QGraphicsScene()
    Frontend(RenderContext(drawing), QtSceneBackend(scene), config=Configuration()).draw_layout(
        drawing.modelspace(), finalize=True
    )
    base = drawing.header.get("$INSBASE", (0.0, 0.0, 0.0))
    return _shapes(scene, base[0], base[1])


def _shapes(scene: qw.QGraphicsScene, base_x: float, base_y: float) -> List[Shape]:
    to_origin = qg.QTransform.fromTranslate(-base_x, -base_y)
    shapes: List[Shape] = []
    for item in scene.items():
        path = qg.QPainterPath()
        filled = False
        if isinstance(item, PointItem):
            path.addEllipse(item._pos, item._radius, item._radius)
            filled = True
        elif isinstance(item, qw.QGraphicsLineItem):
            line = item.line()
            path.moveTo(line.p1())
            path.lineTo(line.p2())
        elif isinstance(item, qw.QGraphicsPathItem):
            path = item.path()
            filled = item.brush().style() != qc.Qt.BrushStyle.NoBrush
        elif isinstance(item, qw.QGraphicsPolygonItem):
            path.addPolygon(item.polygon())
            filled = True
        else:
            continue
        shapes.append((to_origin.map(item.sceneTransform().map(path)), filled))
    return shapes


def outline(shapes: List[Shape]) -> qg.QPainterPath:
    """Every piece of a block as one path - what the insertion preview traces."""
    combined = qg.QPainterPath()
    for path, _filled in shapes:
        combined.addPath(path)
    return combined


def shapes_bounds(shapes: List[Shape]) -> qc.QRectF:
    bounds = qc.QRectF()
    for path, _filled in shapes:
        bounds = bounds.united(path.boundingRect())
    return bounds


def paint_shapes(
    painter: qg.QPainter,
    shapes: List[Shape],
    target: qc.QRectF,
    color: qg.QColor,
    rotation: float = 0.0,
    padding: float = 0.12,
) -> None:
    """Fit a block into `target`, drawing up the right way (the drawing's Y points up)."""
    if not shapes:
        return
    turned = qg.QTransform().rotate(rotation)
    pieces = [(turned.map(path), filled) for path, filled in shapes]
    bounds = shapes_bounds(pieces)
    span = max(bounds.width(), bounds.height(), 1e-9)
    usable = min(target.width(), target.height()) * (1.0 - 2.0 * padding)
    factor = usable / span
    fit = qg.QTransform()
    fit.translate(target.center().x(), target.center().y())
    fit.scale(factor, -factor)
    fit.translate(-bounds.center().x(), -bounds.center().y())

    painter.save()
    painter.setRenderHint(qg.QPainter.RenderHint.Antialiasing)
    pen = qg.QPen(color, 1.2)
    pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
    for path, filled in pieces:
        mapped = fit.map(path)
        if filled:
            painter.fillPath(mapped, color)
        painter.strokePath(mapped, pen)
    painter.restore()


def shapes_pixmap(shapes: List[Shape], size: int, color: qg.QColor, rotation: float = 0.0) -> qg.QPixmap:
    ratio = 2.0
    pixmap = qg.QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(qc.Qt.GlobalColor.transparent)
    painter = qg.QPainter(pixmap)
    paint_shapes(painter, shapes, qc.QRectF(0, 0, size, size), color, rotation)
    painter.end()
    return pixmap
