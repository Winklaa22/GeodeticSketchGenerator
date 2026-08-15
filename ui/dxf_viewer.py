"""Graphical, editable DXF preview panel — renders a DXF drawing the way
AutoCAD's model space does: true layer colors, dashed/dotted linetypes,
filled text, on a dark canvas, with mouse-wheel zoom and click-drag pan —
plus an AutoCAD-style command line for drawing/editing (POINT/LINE/CIRCLE,
ERASE, UNDO/REDO) and view control (ZOOM/PAN/REGEN).

Rendering is delegated to ezdxf's drawing add-on (``Frontend`` +
``RenderContext``), which already resolves layers, blocks, linetypes and
color-by-layer/color-by-block correctly. The only piece implemented here is
the *backend* that turns ezdxf's resolved drawing primitives into
``QGraphicsScene`` items.

ezdxf ships a ready-made PyQt backend (``ezdxf.addons.drawing.pyqt``), but it
is hard-wired through ``ezdxf.addons.xqt`` to PySide6 (falling back to
PyQt5) — this project uses PyQt6 exclusively, and mixing Qt bindings in one
process is not viable. ``QtSceneBackend`` below is a PyQt6 port of that same
backend (same drawing calls, same cosmetic-pen approach), so behaviour and
fidelity match the upstream implementation.

Editing goes exclusively through ``core.dxf_document.DXFDocument`` and
``core.commands.*`` — this module never mutates an ezdxf entity directly, it
only calls document/command methods and re-renders. That keeps undo/redo
correct and keeps ezdxf's entity-lifecycle rules in one place (core/).
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.backend import Backend, BkPath2d, BkPoints2d, ImageData
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing.properties import BackendProperties
from ezdxf.addons.drawing.type_hints import Color
from ezdxf.math import Vec2
from ezdxf.path import Command

from core.commands.base import Command as EditCommand
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand
from core.commands.edit import DeleteEntityCommand
from core.commands.history import CommandHistory
from core.dxf_document import DXFDocument
from ui.theme import Color as UiColor, SPACE_SM, SPACE_XS

_HANDLE_ROLE = qc.Qt.ItemDataRole.UserRole
_CLICK_THRESHOLD_PX = 4


def _x_scale(transform: qg.QTransform) -> float:
    """The transform's scale factor along x — used to keep 'cosmetic' items
    (points) a constant size on screen regardless of the current zoom."""
    return math.sqrt(transform.m11() * transform.m11() + transform.m21() * transform.m21())


def _to_qpainter_path(paths: Iterable[BkPath2d]) -> qg.QPainterPath:
    """Builds a single QPainterPath from one or more ezdxf BkPath2d paths.

    ezdxf ships this exact conversion as ``ezdxf.npshapes.to_qpainter_path``,
    but that helper imports its Qt types from ``ezdxf.addons.xqt``, which only
    recognizes PySide6/PyQt5 — not the PyQt6 this project uses. This is the
    same algorithm, built on PyQt6's own QPainterPath instead.
    """
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


class _PointItem(qw.QAbstractGraphicsShapeItem):
    """A dimensionless DXF POINT, drawn as a small dot of constant pixel size."""

    def __init__(self, x: float, y: float, brush: qg.QBrush) -> None:
        super().__init__()
        self._pos = qc.QPointF(x, y)
        self._radius = 1.2
        self.setPen(qg.QPen(qc.Qt.PenStyle.NoPen))
        self.setBrush(brush)

    def paint(
        self,
        painter: qg.QPainter,
        option: qw.QStyleOptionGraphicsItem,
        widget: Optional[qw.QWidget] = None,
    ) -> None:
        radius = self._radius / _x_scale(painter.transform())
        painter.setBrush(self.brush())
        painter.setPen(qc.Qt.PenStyle.NoPen)
        painter.drawEllipse(self._pos, radius, radius)

    def boundingRect(self) -> qc.QRectF:
        return qc.QRectF(self._pos, qc.QSizeF(1, 1))


class QtSceneBackend(Backend):
    """Turns ezdxf's resolved drawing primitives into QGraphicsScene items."""

    def __init__(self, scene: qw.QGraphicsScene) -> None:
        super().__init__()
        self._scene = scene
        self._color_cache: dict = {}
        self._no_line = qg.QPen(qc.Qt.PenStyle.NoPen)
        self._no_fill = qg.QBrush(qc.Qt.BrushStyle.NoBrush)

    def configure(self, config: Configuration) -> None:
        if config.min_lineweight is None:
            config = config.with_changes(min_lineweight=0.24)
        super().configure(config)

    def _add(self, item: qw.QGraphicsItem, handle: str) -> None:
        # Tag every item with its DXF entity handle so a canvas click can be
        # mapped back to a real entity — see CadGraphicsView's hit-testing.
        item.setData(_HANDLE_ROLE, handle)
        self._scene.addItem(item)

    def _qcolor(self, color: Color) -> qg.QColor:
        cached = self._color_cache.get(color)
        if cached is not None:
            return cached
        if len(color) == 7:
            qcolor = qg.QColor(color)  # '#RRGGBB'
        elif len(color) == 9:
            qcolor = qg.QColor(f"#{color[7:9]}{color[1:7]}")  # '#AARRGGBB'
        else:
            raise ValueError(f"unsupported color format: {color!r}")
        self._color_cache[color] = qcolor
        return qcolor

    def _pen(self, properties: BackendProperties) -> qg.QPen:
        """A cosmetic pen (constant width in pixels, independent of zoom)."""
        px = properties.lineweight / 0.3527 * self.config.lineweight_scaling
        pen = qg.QPen(self._qcolor(properties.color), px)
        pen.setCosmetic(True)
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        return pen

    def _fill_brush(self, color: Color) -> qg.QBrush:
        return qg.QBrush(self._qcolor(color), qc.Qt.BrushStyle.SolidPattern)

    def set_background(self, color: Color) -> None:
        self._scene.setBackgroundBrush(qg.QBrush(self._qcolor(color)))

    def draw_point(self, pos: Vec2, properties: BackendProperties) -> None:
        self._add(_PointItem(pos.x, pos.y, self._fill_brush(properties.color)), properties.handle)

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
        item = qw.QGraphicsPathItem(_to_qpainter_path([path]))
        item.setPen(self._pen(properties))
        item.setBrush(self._no_fill)
        self._add(item, properties.handle)

    def draw_filled_paths(
        self, paths: Iterable[BkPath2d], properties: BackendProperties
    ) -> None:
        paths = list(paths)
        if not paths:
            return
        item = qw.QGraphicsPathItem(_to_qpainter_path(paths))
        item.setPen(self._pen(properties))
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
        # Raster IMAGE/WIPEOUT entities are rare in survey/point DXFs and are
        # skipped rather than decoded — everything else still renders.
        return

    def clear(self) -> None:
        self._scene.clear()

    def finalize(self) -> None:
        super().finalize()
        self._scene.setSceneRect(self._scene.itemsBoundingRect())


class CadGraphicsView(qw.QGraphicsView):
    """Pannable, zoomable, editable canvas mirroring AutoCAD's viewport:
    scroll wheel zooms under the cursor, click-drag pans, a plain click
    selects an entity (or places a point for the active draw tool) — and the
    same operations are exposed as plain methods so the command line (ZOOM,
    PAN, POINT, LINE, ...) can drive the view too.
    """

    entitySelected = qc.pyqtSignal(object)  # str handle, or None for "clicked empty space"
    toolPointPlaced = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._base_scale = 1.0  # x_scale() right after the last fit_to_scene — the "1.0x" reference
        self._min_zoom = 0.02
        self._max_zoom = 200.0
        self._zoom_step = 0.2
        self._tool: Optional["ToolSession"] = None
        self._press_pos: Optional[qc.QPoint] = None
        self._selected_item: Optional[qw.QGraphicsItem] = None

        self.setObjectName("dxfCanvas")
        self.setTransformationAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(qw.QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(qc.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(qw.QFrame.Shape.NoFrame)
        self.setRenderHints(
            qg.QPainter.RenderHint.Antialiasing
            | qg.QPainter.RenderHint.TextAntialiasing
            | qg.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setScene(qw.QGraphicsScene(self))
        self.scale(1, -1)  # DXF space is Y-up; Qt's scene is Y-down.

    def _current_zoom(self) -> float:
        return _x_scale(self.transform()) / (self._base_scale or 1.0)

    def fit_to_scene(self) -> None:
        """AutoCAD's ZOOM EXTENTS: frames every entity, becomes the new 1.0x."""
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        margin = (max(rect.width(), rect.height()) * 0.04) or 1.0
        rect = rect.adjusted(-margin, -margin, margin, margin)
        self.setSceneRect(rect)
        self.fitInView(rect, qc.Qt.AspectRatioMode.KeepAspectRatio)
        self._base_scale = _x_scale(self.transform())

    def zoom_by(self, factor: float) -> bool:
        """Scales the view by `factor` around its center. Returns False (and
        does nothing) if that would exceed the zoom limits."""
        if factor <= 0:
            return False
        resulting_zoom = self._current_zoom() * factor
        if resulting_zoom < self._min_zoom or resulting_zoom > self._max_zoom:
            return False
        self.scale(factor, factor)
        return True

    def zoom_window(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        """AutoCAD's ZOOM WINDOW: frames the box between two scene points."""
        rect = qc.QRectF(qc.QPointF(*p1), qc.QPointF(*p2)).normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        self.fitInView(rect, qc.Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def pan_by(self, dx: float, dy: float) -> None:
        """Recenters the view `dx, dy` scene units away — same units as the
        drawing itself, so PAN 10,0 always moves by 10 drawing units."""
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center.x() + dx, center.y() + dy)

    def save_view(self) -> Tuple[qg.QTransform, int, int]:
        """Captures the current transform + scroll position, so a full scene
        rebuild (after an edit) can put the user back where they were."""
        return self.transform(), self.horizontalScrollBar().value(), self.verticalScrollBar().value()

    def restore_view(self, saved: Tuple[qg.QTransform, int, int]) -> None:
        transform, h_value, v_value = saved
        self.setTransform(transform)
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)

    def wheelEvent(self, event: qg.QWheelEvent) -> None:  # noqa: N802 (Qt override)
        notches = event.angleDelta().y() / 120
        if notches == 0:
            return
        factor = (1.0 + self._zoom_step) ** notches
        self.zoom_by(factor)

    # ------------------------------------------------------------------
    # Editing: tool mode + click-to-select
    # ------------------------------------------------------------------
    def set_tool(self, tool: Optional["ToolSession"]) -> None:
        """Activates (or, with None, deactivates) an interactive draw tool.
        While a tool is active, clicks place points instead of panning."""
        self._tool = tool
        active = tool is not None
        self.setDragMode(
            qw.QGraphicsView.DragMode.NoDrag if active else qw.QGraphicsView.DragMode.ScrollHandDrag
        )
        self.setCursor(qc.Qt.CursorShape.CrossCursor if active else qc.Qt.CursorShape.ArrowCursor)

    def set_selected_item(self, item: Optional[qw.QGraphicsItem]) -> None:
        self._selected_item = item
        self.viewport().update()

    def mousePressEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        if self._tool is not None:
            point = self.mapToScene(event.position().toPoint())
            self._tool.update_preview((point.x(), point.y()), self.scene())

    def mouseReleaseEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if event.button() != qc.Qt.MouseButton.LeftButton or self._press_pos is None:
            return
        release_pos = event.position().toPoint()
        moved = (release_pos - self._press_pos).manhattanLength()
        self._press_pos = None
        if moved > _CLICK_THRESHOLD_PX:
            return  # a pan drag, not a click
        scene_point = self.mapToScene(release_pos)
        if self._tool is not None:
            self._tool.on_click((scene_point.x(), scene_point.y()))
            self.toolPointPlaced.emit()
        else:
            item = self._topmost_handled_item(release_pos)
            handle = item.data(_HANDLE_ROLE) if item is not None else None
            self.set_selected_item(item)
            self.entitySelected.emit(handle)

    def _topmost_handled_item(self, view_pos: qc.QPoint) -> Optional[qw.QGraphicsItem]:
        # A few-pixel tolerance box, in device space, so it stays easy to hit
        # a POINT or a thin line regardless of the current zoom level.
        tolerance = 4
        rect = qc.QRect(view_pos.x() - tolerance, view_pos.y() - tolerance, tolerance * 2, tolerance * 2)
        for item in self.items(rect):
            if item.data(_HANDLE_ROLE) is not None:
                return item
        return None

    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:  # noqa: N802
        if self._selected_item is None:
            return
        highlight_rect = self._selected_item.sceneTransform().mapRect(self._selected_item.boundingRect())
        color = qg.QColor(UiColor.ACCENT)
        color.setAlpha(90)
        painter.fillRect(highlight_rect, color)


# --------------------------------------------------------------------------
# Coordinate entry — the command line accepts absolute "x,y", relative
# "@dx,dy" and relative-polar "@distance<angle_deg", same grammar AutoCAD
# uses (the polar form is the one survey data naturally comes in: a bearing
# and a distance).
# --------------------------------------------------------------------------
def _parse_coordinate(text: str, last_point: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    text = text.strip()
    if not text:
        return None
    if text.startswith("@"):
        if last_point is None:
            return None
        body = text[1:]
        if "<" in body:
            dist_str, _, angle_str = body.partition("<")
            try:
                distance, angle_deg = float(dist_str), float(angle_str)
            except ValueError:
                return None
            angle = math.radians(angle_deg)
            return (
                last_point[0] + distance * math.cos(angle),
                last_point[1] + distance * math.sin(angle),
            )
        x_str, _, y_str = body.partition(",")
        if not y_str:
            return None
        try:
            dx, dy = float(x_str), float(y_str)
        except ValueError:
            return None
        return (last_point[0] + dx, last_point[1] + dy)
    x_str, _, y_str = text.partition(",")
    if not y_str:
        return None
    try:
        return (float(x_str), float(y_str))
    except ValueError:
        return None


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


# --------------------------------------------------------------------------
# Interactive draw tools — collect points via canvas clicks or typed command
# -line text, then hand back a Command for DxfViewer to run through history.
# --------------------------------------------------------------------------
class ToolSession:
    """Base class for one interactive draw command's placement state."""

    def __init__(self) -> None:
        self.prompt: str = ""

    def on_click(self, point: Tuple[float, float]) -> None:
        raise NotImplementedError

    def on_text(self, text: str) -> Optional[str]:
        """Handles typed command-line input for the current step. Returns an
        error message to show (leaving the step unchanged), or None once the
        input was accepted."""
        raise NotImplementedError

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        """Called on every mouse move; override to draw a rubber-band preview."""

    def is_done(self) -> bool:
        raise NotImplementedError

    def build_command(self) -> EditCommand:
        raise NotImplementedError

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        """Removes any preview item this session added to the scene."""


def _preview_pen() -> qg.QPen:
    pen = qg.QPen(qg.QColor(UiColor.ACCENT))
    pen.setCosmetic(True)
    pen.setStyle(qc.Qt.PenStyle.DashLine)
    return pen


class PointToolSession(ToolSession):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = "Specify point: "
        self._point: Optional[Tuple[float, float]] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        self._point = point

    def on_text(self, text: str) -> Optional[str]:
        coord = _parse_coordinate(text, last_point=None)
        if coord is None:
            return f'Point must be given as "x,y": "{text}".'
        self._point = coord
        return None

    def is_done(self) -> bool:
        return self._point is not None

    def build_command(self) -> EditCommand:
        assert self._point is not None
        return AddPointCommand(self._point)


class LineToolSession(ToolSession):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = "Specify first point: "
        self._start: Optional[Tuple[float, float]] = None
        self._end: Optional[Tuple[float, float]] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._start is None:
            self._start = point
            self.prompt = "Specify next point: "
        else:
            self._end = point

    def on_text(self, text: str) -> Optional[str]:
        coord = _parse_coordinate(text, last_point=self._start)
        if coord is None:
            return f'Point must be given as "x,y" or "@dx,dy": "{text}".'
        if self._start is None:
            self._start = coord
            self.prompt = "Specify next point: "
        else:
            self._end = coord
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._start is None or self._end is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(_preview_pen())
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._start[0], self._start[1], point[0], point[1])

    def is_done(self) -> bool:
        return self._start is not None and self._end is not None

    def build_command(self) -> EditCommand:
        assert self._start is not None and self._end is not None
        return AddLineCommand(self._start, self._end)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None


class CircleToolSession(ToolSession):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = "Specify center point: "
        self._center: Optional[Tuple[float, float]] = None
        self._radius: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsEllipseItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._center is None:
            self._center = point
            self.prompt = "Specify radius (or a point): "
        else:
            self._radius = _distance(self._center, point)

    def on_text(self, text: str) -> Optional[str]:
        if self._center is None:
            coord = _parse_coordinate(text, last_point=None)
            if coord is None:
                return f'Point must be given as "x,y": "{text}".'
            self._center = coord
            self.prompt = "Specify radius (or a point): "
            return None
        try:
            radius = float(text.strip())
        except ValueError:
            coord = _parse_coordinate(text, last_point=self._center)
            if coord is None:
                return f'Requires a numeric radius or a point: "{text}".'
            radius = _distance(self._center, coord)
        if radius <= 0:
            return "Radius must be positive."
        self._radius = radius
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._center is None or self._radius is not None:
            return
        radius = _distance(self._center, point)
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsEllipseItem()
            self._preview_item.setPen(_preview_pen())
            scene.addItem(self._preview_item)
        cx, cy = self._center
        self._preview_item.setRect(cx - radius, cy - radius, radius * 2, radius * 2)

    def is_done(self) -> bool:
        return self._center is not None and self._radius is not None

    def build_command(self) -> EditCommand:
        assert self._center is not None and self._radius is not None
        return AddCircleCommand(self._center, self._radius)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None


class CommandLine(qw.QWidget):
    """AutoCAD-style command line: a short scrollback of echoed commands and
    responses, docked above a single "Command:" input — sits right under the
    drawing canvas, exactly where AutoCAD puts it."""

    commandEntered = qc.pyqtSignal(str)
    undoRequested = qc.pyqtSignal()
    redoRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dxfCommandLine")
        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._history = qw.QPlainTextEdit()
        self._history.setObjectName("dxfCommandHistory")
        self._history.setReadOnly(True)
        self._history.setFixedHeight(52)
        self._history.setLineWrapMode(qw.QPlainTextEdit.LineWrapMode.NoWrap)
        self._history.setVerticalScrollBarPolicy(qc.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history.setFocusPolicy(qc.Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._history)

        input_row = qw.QWidget()
        input_row.setObjectName("dxfCommandInputRow")
        input_layout = qw.QHBoxLayout(input_row)
        input_layout.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        input_layout.setSpacing(SPACE_XS)
        prompt = qw.QLabel("Command:")
        prompt.setObjectName("dxfCommandPrompt")
        self._input = qw.QLineEdit()
        self._input.setObjectName("dxfCommandInput")
        self._input.setPlaceholderText("POINT, LINE, CIRCLE, ZOOM …")
        self._input.returnPressed.connect(self._submit)
        # QLineEdit binds Ctrl+Z/Ctrl+Y to its own internal text-edit undo/redo
        # and consumes the key press before any parent QShortcut sees it — an
        # event filter runs first, so it's the only reliable way to redirect
        # those keys to the drawing's undo/redo while focus is in this field.
        self._input.installEventFilter(self)
        input_layout.addWidget(prompt)
        input_layout.addWidget(self._input, 1)
        layout.addWidget(input_row)

        self.reset()

    def eventFilter(self, obj: qc.QObject, event: qc.QEvent) -> bool:  # noqa: N802
        if obj is self._input and event.type() == qc.QEvent.Type.KeyPress:
            key_event = event
            if key_event.modifiers() & qc.Qt.KeyboardModifier.ControlModifier:
                is_shift = bool(key_event.modifiers() & qc.Qt.KeyboardModifier.ShiftModifier)
                if key_event.key() == qc.Qt.Key.Key_Z and not is_shift:
                    self.undoRequested.emit()
                    return True
                if key_event.key() == qc.Qt.Key.Key_Y or (key_event.key() == qc.Qt.Key.Key_Z and is_shift):
                    self.redoRequested.emit()
                    return True
        return super().eventFilter(obj, event)

    def reset(self) -> None:
        self._history.clear()
        self._echo("Type POINT, LINE, CIRCLE, ERASE, U(ndo), REDO, ZOOM, PAN or REGEN.")

    def show_response(self, message: str) -> None:
        if message:
            self._echo(message)

    def set_placeholder(self, text: str) -> None:
        self._input.setPlaceholderText(text)

    def _submit(self) -> None:
        text = self._input.text().strip()
        self._input.clear()
        if not text:
            return
        self._echo(f"Command: {text}")
        self.commandEntered.emit(text)

    def _echo(self, line: str) -> None:
        self._history.appendPlainText(line)
        scrollbar = self._history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class _CommandError(Exception):
    """Raised by a command handler for a malformed argument; the message is
    shown in the command line, same as an invalid AutoCAD command prompt."""


class DxfCommandInterpreter:
    """Parses a small set of AutoCAD-style commands: view control
    (ZOOM/PAN/REGEN, applied directly to the CadGraphicsView) and editing
    (POINT/LINE/CIRCLE/ERASE/UNDO/REDO, applied through the owning
    DxfViewer's DXFDocument + CommandHistory)."""

    def __init__(self, dxf_viewer: "DxfViewer") -> None:
        self._viewer = dxf_viewer
        self._view = dxf_viewer.view
        self._last_command: Optional[str] = None
        self._commands = {
            "ZOOM": self._cmd_zoom,
            "Z": self._cmd_zoom,
            "PAN": self._cmd_pan,
            "P": self._cmd_pan,
            "REGEN": self._cmd_regen,
            "RE": self._cmd_regen,
            "REDRAW": self._cmd_regen,
            "POINT": self._cmd_point,
            "PO": self._cmd_point,
            "LINE": self._cmd_line,
            "L": self._cmd_line,
            "CIRCLE": self._cmd_circle,
            "C": self._cmd_circle,
            "ERASE": self._cmd_erase,
            "DELETE": self._cmd_erase,
            "E": self._cmd_erase,
            "U": self._cmd_undo,
            "UNDO": self._cmd_undo,
            "REDO": self._cmd_redo,
        }

    def run(self, text: str) -> str:
        """Executes one command line and returns the response to echo back
        (an empty string means "ran silently", like most AutoCAD commands)."""
        text = text.strip()
        if not text:
            if self._last_command is None:
                return ""
            text = self._last_command  # bare Enter repeats the last command
        name, *args = text.split()
        handler = self._commands.get(name.upper())
        if handler is None:
            return f'Unknown command "{name}". Press F1 for help.'
        self._last_command = text
        try:
            return handler(args)
        except _CommandError as exc:
            return str(exc)

    # -- view commands (no document, no undo) --------------------------
    def _cmd_zoom(self, args: List[str]) -> str:
        if not args:
            return "Specify a scale factor, or [Extents/Window]:"
        keyword = args[0].upper()
        if keyword in ("E", "EXTENTS", "A", "ALL"):
            self._view.fit_to_scene()
            return ""
        if keyword in ("W", "WINDOW"):
            p1, p2 = self._parse_points(args[1:], count=2)
            if not self._view.zoom_window(p1, p2):
                raise _CommandError("Invalid zoom window.")
            return ""
        if keyword == "IN":
            return "" if self._view.zoom_by(1.25) else "Zoom limit reached."
        if keyword == "OUT":
            return "" if self._view.zoom_by(0.8) else "Zoom limit reached."
        factor = self._parse_factor(args[0])
        return "" if self._view.zoom_by(factor) else "Zoom limit reached."

    def _cmd_pan(self, args: List[str]) -> str:
        if not args:
            return "Click and drag with the left mouse button to pan, or use PAN dx,dy."
        dx, dy = self._parse_point(args[0])
        self._view.pan_by(dx, dy)
        return ""

    def _cmd_regen(self, args: List[str]) -> str:
        return "Regenerating model."

    # -- editing commands (through DXFDocument + CommandHistory) -------
    def _cmd_point(self, args: List[str]) -> str:
        if args:
            coord = _parse_coordinate(args[0], last_point=None)
            if coord is None:
                raise _CommandError(f'Point must be given as "x,y": "{args[0]}".')
            self._viewer.execute_command(AddPointCommand(coord))
            return ""
        self._viewer.start_tool(PointToolSession())
        return ""

    def _cmd_line(self, args: List[str]) -> str:
        if len(args) >= 2:
            start = _parse_coordinate(args[0], last_point=None)
            end = _parse_coordinate(args[1], last_point=start)
            if start is None or end is None:
                raise _CommandError(f'Points must be given as "x,y": "{args[0]} {args[1]}".')
            self._viewer.execute_command(AddLineCommand(start, end))
            return ""
        self._viewer.start_tool(LineToolSession())
        return ""

    def _cmd_circle(self, args: List[str]) -> str:
        if len(args) >= 2:
            center = _parse_coordinate(args[0], last_point=None)
            if center is None:
                raise _CommandError(f'Point must be given as "x,y": "{args[0]}".')
            try:
                radius = float(args[1])
            except ValueError:
                raise _CommandError(f'Requires a numeric radius: "{args[1]}".') from None
            if radius <= 0:
                raise _CommandError("Radius must be positive.")
            self._viewer.execute_command(AddCircleCommand(center, radius))
            return ""
        self._viewer.start_tool(CircleToolSession())
        return ""

    def _cmd_erase(self, args: List[str]) -> str:
        return self._viewer.delete_selected()

    def _cmd_undo(self, args: List[str]) -> str:
        return self._viewer.undo()

    def _cmd_redo(self, args: List[str]) -> str:
        return self._viewer.redo()

    # -- shared parsing --------------------------------------------------
    @staticmethod
    def _parse_factor(token: str) -> float:
        try:
            factor = float(token.upper().rstrip("X"))
        except ValueError:
            raise _CommandError(f'Requires a numeric value: "{token}".') from None
        if factor <= 0:
            raise _CommandError("Scale factor must be positive.")
        return factor

    @staticmethod
    def _parse_point(token: str) -> Tuple[float, float]:
        x_str, _, y_str = token.partition(",")
        try:
            return float(x_str), float(y_str)
        except ValueError:
            raise _CommandError(f'Point must be given as "x,y": "{token}".') from None

    @classmethod
    def _parse_points(cls, tokens: List[str], count: int) -> List[Tuple[float, float]]:
        if len(tokens) < count:
            raise _CommandError("Point not specified.")
        return [cls._parse_point(t) for t in tokens[:count]]


class DxfViewer(qw.QWidget):
    """Stacked empty-state / interactive, editable DXF canvas for the
    preview panel — draw/select/delete with undo/redo, backed by a real
    DXFDocument + CommandHistory (see core/dxf_document.py, core/commands/)."""

    documentChanged = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.entity_count = 0
        self.layer_count = 0
        self._doc: Optional[DXFDocument] = None
        self._history: Optional[CommandHistory] = None
        self._active_tool: Optional[ToolSession] = None
        self._selected_handle: Optional[str] = None

        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = qw.QStackedWidget()
        layout.addWidget(self._stack)

        self._empty_page = qw.QWidget()
        self._empty_page.setObjectName("dxfEmpty")
        empty_layout = qw.QVBoxLayout(self._empty_page)
        empty_layout.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(SPACE_SM)
        icon = qw.QLabel("⬡")
        icon.setObjectName("dxfEmptyIcon")
        icon.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        text = qw.QLabel("Load a .DXF file, or press Apply to DXF to start a new drawing.")
        text.setObjectName("dxfEmptyText")
        text.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon)
        empty_layout.addWidget(text)

        # The canvas and the command line are docked together as one block,
        # same as AutoCAD's drawing window + command line underneath it.
        self._canvas_page = qw.QWidget()
        canvas_layout = qw.QVBoxLayout(self._canvas_page)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self._view = CadGraphicsView()
        self._view.entitySelected.connect(self._on_entity_selected)
        self._view.toolPointPlaced.connect(self._on_tool_point_placed)
        self._command_line = CommandLine()
        self._command_line.commandEntered.connect(self._on_command_entered)
        self._command_line.undoRequested.connect(lambda: self._echo(self.undo()))
        self._command_line.redoRequested.connect(lambda: self._echo(self.redo()))
        canvas_layout.addWidget(self._view, 1)
        canvas_layout.addWidget(self._command_line)

        self._interpreter = DxfCommandInterpreter(self)

        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._canvas_page)

        # Widget-scoped shortcuts: fire whether focus is on the canvas or
        # the command-line input, as long as it's somewhere in this panel.
        self._add_shortcut("Ctrl+Z", lambda: self._echo(self.undo()))
        self._add_shortcut("Ctrl+Y", lambda: self._echo(self.redo()))
        self._add_shortcut("Delete", lambda: self._echo(self.delete_selected()))
        self._add_shortcut("Esc", self.cancel_tool)

    def _add_shortcut(self, sequence: str, slot) -> None:
        shortcut = qg.QShortcut(qg.QKeySequence(sequence), self)
        shortcut.setContext(qc.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(slot)

    @property
    def view(self) -> CadGraphicsView:
        return self._view

    @property
    def has_document(self) -> bool:
        return self._doc is not None

    def save_document(self, file_path: str) -> None:
        assert self._doc is not None
        self._doc.save(file_path)

    def ensure_document(self) -> DXFDocument:
        """Returns the current document, creating a blank one first if none
        is loaded yet — so drawing commands always have somewhere to go."""
        if self._doc is None:
            self._doc = DXFDocument.new()
            self._history = CommandHistory()
            self._selected_handle = None
            self._render(preserve_view=False)
            self._command_line.reset()
            self._stack.setCurrentWidget(self._canvas_page)
        return self._doc

    def show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty_page)

    def clear(self) -> None:
        self.cancel_tool()
        self._view.scene().clear()
        self._view.set_selected_item(None)
        self.entity_count = 0
        self.layer_count = 0
        self._doc = None
        self._history = None
        self._selected_handle = None
        self.show_empty()

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """Loads and renders `file_path`. Returns (success, error_message)."""
        try:
            doc = DXFDocument.load(file_path)
        except IOError as exc:
            return False, f"Could not read file: {exc}"
        except ezdxf.DXFError as exc:
            return False, f"Not a valid DXF file: {exc}"

        self._doc = doc
        self._history = CommandHistory()
        self._selected_handle = None
        try:
            self._render(preserve_view=False)
        except Exception as exc:  # noqa: BLE001 - a bad/unsupported drawing must never crash the app
            self._doc = None
            self._history = None
            return False, f"Could not render drawing: {exc}"

        self._command_line.reset()
        self._stack.setCurrentWidget(self._canvas_page)
        return True, ""

    # ------------------------------------------------------------------
    # Editing API — used by DxfCommandInterpreter and the shortcuts above.
    # ------------------------------------------------------------------
    def execute_command(self, command: EditCommand) -> None:
        self.ensure_document()
        assert self._doc is not None and self._history is not None
        self._history.execute(command, self._doc)
        self._render(preserve_view=True)

    def undo(self) -> str:
        if self._doc is None or self._history is None or not self._history.undo(self._doc):
            return "Nothing to undo."
        self.clear_selection()
        self._render(preserve_view=True)
        return ""

    def redo(self) -> str:
        if self._doc is None or self._history is None or not self._history.redo(self._doc):
            return "Nothing to redo."
        self.clear_selection()
        self._render(preserve_view=True)
        return ""

    def delete_selected(self) -> str:
        if self._selected_handle is None:
            return "Select an object first."
        self.execute_command(DeleteEntityCommand([self._selected_handle]))
        self.clear_selection()
        return ""

    def clear_selection(self) -> None:
        self._selected_handle = None
        self._view.set_selected_item(None)

    def start_tool(self, tool: ToolSession) -> None:
        self.cancel_tool()
        self.clear_selection()
        self._active_tool = tool
        self._view.set_tool(tool)
        self._command_line.show_response(tool.prompt)

    def cancel_tool(self) -> None:
        if self._active_tool is not None:
            self._active_tool.cleanup(self._view.scene())
            self._active_tool = None
            self._view.set_tool(None)
            self._command_line.show_response("Cancelled.")
        self.clear_selection()

    # ------------------------------------------------------------------
    # Internal signal handlers
    # ------------------------------------------------------------------
    def _on_command_entered(self, text: str) -> None:
        if self._active_tool is not None:
            message = self._active_tool.on_text(text)
            if message:
                self._command_line.show_response(message)
            elif self._active_tool.is_done():
                self._finish_tool()
            else:
                self._command_line.show_response(self._active_tool.prompt)
            return
        response = self._interpreter.run(text)
        self._command_line.show_response(response)

    def _on_tool_point_placed(self) -> None:
        if self._active_tool is None:
            return
        if self._active_tool.is_done():
            self._finish_tool()
        else:
            self._command_line.show_response(self._active_tool.prompt)

    def _on_entity_selected(self, handle: object) -> None:
        self._selected_handle = handle  # type: ignore[assignment]

    def _finish_tool(self) -> None:
        tool = self._active_tool
        assert tool is not None
        command = tool.build_command()
        tool.cleanup(self._view.scene())
        self._active_tool = None
        self._view.set_tool(None)
        self.execute_command(command)

    def _echo(self, message: str) -> None:
        self._command_line.show_response(message)

    def _render(self, *, preserve_view: bool) -> None:
        assert self._doc is not None
        saved = self._view.save_view() if preserve_view else None
        scene = qw.QGraphicsScene()
        backend = QtSceneBackend(scene)
        context = RenderContext(self._doc.drawing)
        Frontend(context, backend, config=Configuration()).draw_layout(self._doc.modelspace, finalize=True)
        self._view.setScene(scene)
        if saved is not None:
            self._view.restore_view(saved)
        else:
            self._view.fit_to_scene()
        self.entity_count = self._doc.entity_count()
        self.layer_count = self._doc.layer_count()
        self.documentChanged.emit()
