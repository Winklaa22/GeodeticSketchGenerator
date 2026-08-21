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
from typing import Callable, Dict, Iterable, List, Optional, Tuple

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
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand, AddTextCommand
from core.commands.edit import DeleteEntityCommand, MoveCommand
from core.commands.history import CommandHistory
from core.commands.composite import CompositeCommand
from core.commands.layers import (
    AddLayerCommand,
    DeleteLayerCommand,
    SetActiveLayerCommand,
    SetLayerColorCommand,
    SetLayerVisibleCommand,
    layers_to_prune,
)
from core.commands.text import (
    SetEntityColorCommand,
    SetTextContentCommand,
    SetTextHeightCommand,
    SetTextRotationCommand,
)
from core.dxf_document import DXFDocument
from ui.layer_panel import LayerPanel
from ui.theme import Color as UiColor, SPACE_SM, SPACE_XS
from ui.widgets import ColorSwatchButton, decimal_validator

_HANDLE_ROLE = qc.Qt.ItemDataRole.UserRole
_CLICK_THRESHOLD_PX = 4
_SNAP_TOLERANCE_PX = 14  # "aim assist" radius for snapping to an existing POINT or LINE endpoint


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
        r = 0.01
        return qc.QRectF(self._pos.x() - r, self._pos.y() - r, r * 2, r * 2)


def _distance_to_segment(point: qc.QPointF, line: qc.QLineF) -> float:
    p1, p2 = line.p1(), line.p2()
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(point.x() - p1.x(), point.y() - p1.y())
    t = ((point.x() - p1.x()) * dx + (point.y() - p1.y()) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    proj_x, proj_y = p1.x() + t * dx, p1.y() + t * dy
    return math.hypot(point.x() - proj_x, point.y() - proj_y)


def _distance_to_item(point: qc.QPointF, item: qw.QGraphicsItem) -> float:
    """Distance from `point` (scene coords) to an item's true reference
    geometry — used to pick the closest match among several overlapping
    candidates instead of trusting each item's own shape()/boundingRect(),
    which can be inflated well beyond what it actually looks like on screen
    (see _PointItem.boundingRect above; QGraphicsLineItem has the same
    issue via its cosmetic pen's width)."""
    if isinstance(item, _PointItem):
        return math.hypot(point.x() - item._pos.x(), point.y() - item._pos.y())
    if isinstance(item, qw.QGraphicsLineItem):
        return _distance_to_segment(point, item.line())
    center = item.sceneTransform().mapRect(item.boundingRect()).center()
    return math.hypot(point.x() - center.x(), point.y() - center.y())


def _snap_candidates(item: qw.QGraphicsItem) -> Tuple[qc.QPointF, ...]:
    """The exact scene points a draw tool's "aim assist" may snap to for
    `item`: a POINT's own position, or a LINE's two endpoints — the same
    entities/coordinates AutoCAD's ENDPOINT/NODE object snaps target."""
    if isinstance(item, _PointItem):
        return (item._pos,)
    if isinstance(item, qw.QGraphicsLineItem):
        line = item.line()
        return (line.p1(), line.p2())
    return ()


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
    scroll wheel zooms under the cursor, middle-button-drag pans, left-click
    selects an entity (Shift+click adds/removes), left-drag on empty space
    opens a window-select box, and the same operations are exposed as plain
    methods so the command line (ZOOM, PAN, POINT, LINE, ...) can drive the
    view too.
    """

    entitySelected = qc.pyqtSignal(list)  # list[str] of handles, [] for "nothing selected"
    toolPointPlaced = qc.pyqtSignal()
    itemsDragMoved = qc.pyqtSignal(list, float, float)  # handles, dx, dy — see _finish_drag_items
    viewportChanged = qc.pyqtSignal()  # transform or scroll position changed — see TextOptionsBar

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._base_scale = 1.0  # x_scale() right after the last fit_to_scene — the "1.0x" reference
        self._min_zoom = 0.02
        self._max_zoom = 200.0
        self._zoom_step = 0.2
        self._tool: Optional["ToolSession"] = None
        self._press_pos: Optional[qc.QPoint] = None
        self._selected_items: List[qw.QGraphicsItem] = []
        self._pan_last_pos: Optional[qc.QPoint] = None
        self._rubber_band: Optional[qw.QRubberBand] = None
        self._snap_indicator: Optional[qc.QPointF] = None
        self._doc: Optional[DXFDocument] = None
        # Click-and-drag move (no tool active, press starts on an entity) —
        # see mousePressEvent/_ensure_dragging_items/_finish_drag_items.
        self._drag_candidate: Optional[qw.QGraphicsItem] = None
        self._dragging_items = False
        self._drag_items: List[qw.QGraphicsItem] = []
        self._drag_start_scene: Optional[qc.QPointF] = None

        self.setObjectName("dxfCanvas")
        # So DxfViewer._finish_tool can return focus here (away from the
        # command line) once a tool session ends — see setFocus() there.
        self.setFocusPolicy(qc.Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Panning is handled manually via the middle mouse button (see
        # mouse*Event below) so the left button is free for click/window
        # select — NoDrag stays in effect the whole time, tool or not.
        self.setDragMode(qw.QGraphicsView.DragMode.NoDrag)
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
        self.viewportChanged.emit()

    def zoom_by(self, factor: float) -> bool:
        """Scales the view by `factor` around its center. Returns False (and
        does nothing) if that would exceed the zoom limits."""
        if factor <= 0:
            return False
        resulting_zoom = self._current_zoom() * factor
        if resulting_zoom < self._min_zoom or resulting_zoom > self._max_zoom:
            return False
        self.scale(factor, factor)
        self.viewportChanged.emit()
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
        self.viewportChanged.emit()

    def save_view(self) -> Tuple[qg.QTransform, int, int]:
        """Captures the current transform + scroll position, so a full scene
        rebuild (after an edit) can put the user back where they were."""
        return self.transform(), self.horizontalScrollBar().value(), self.verticalScrollBar().value()

    def restore_view(self, saved: Tuple[qg.QTransform, int, int]) -> None:
        transform, h_value, v_value = saved
        self.setTransform(transform)
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)
        self.viewportChanged.emit()

    def resizeEvent(self, event: qg.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.viewportChanged.emit()

    def wheelEvent(self, event: qg.QWheelEvent) -> None:  # noqa: N802 (Qt override)
        notches = event.angleDelta().y() / 120
        if notches == 0:
            return
        factor = (1.0 + self._zoom_step) ** notches
        self.zoom_by(factor)

    # ------------------------------------------------------------------
    # Editing: tool mode + click/window-select + middle-button pan
    # ------------------------------------------------------------------
    def set_tool(self, tool: Optional["ToolSession"]) -> None:
        """Activates (or, with None, deactivates) an interactive draw tool.
        While a tool is active, clicks place points instead of selecting."""
        self._tool = tool
        self.setCursor(qc.Qt.CursorShape.CrossCursor if tool is not None else qc.Qt.CursorShape.ArrowCursor)
        if tool is None:
            self._set_snap_indicator(None)

    def set_document(self, doc: Optional[DXFDocument]) -> None:
        """Keeps the aim-assist snap in sync with the live document — needed
        to resolve a CIRCLE item's true center (see `_snap_candidates_for`),
        which isn't recoverable from its rendered Qt geometry alone."""
        self._doc = doc

    def _snap_candidates_for(
        self, item: qw.QGraphicsItem, raw_scene_point: qc.QPointF
    ) -> Tuple[Tuple[qc.QPointF, qc.QPointF], ...]:
        """The (hover_point, snap_point) pairs a draw tool's "aim assist" may
        offer for `item`: `hover_point` is compared against the cursor to
        decide whether this candidate is close enough to trigger at all;
        `snap_point` is the exact coordinate the cursor then locks onto.

        For a POINT or a LINE endpoint these are the same spot — you hover
        the exact feature. For a CIRCLE (survey points are drawn as small
        circles — see core.commands.survey.build_points_command) they
        differ: what you actually see and naturally hover is the visible
        ring, not its centre, but the snap should still lock onto the
        centre — same as AutoCAD's CENTER object snap."""
        plain = _snap_candidates(item)
        if plain:
            return tuple((point, point) for point in plain)
        if self._doc is None:
            return ()
        handle = item.data(_HANDLE_ROLE)
        entity = self._doc.get_entity(handle) if handle else None
        if entity is None or entity.dxftype() != "CIRCLE":
            return ()
        center = entity.dxf.center
        center_point = qc.QPointF(center.x, center.y)
        radius = entity.dxf.radius
        dx, dy = raw_scene_point.x() - center_point.x(), raw_scene_point.y() - center_point.y()
        dist_to_center = math.hypot(dx, dy)
        if radius <= 0 or dist_to_center <= 0:
            hover_point = center_point
        else:
            hover_point = qc.QPointF(
                center_point.x() + dx / dist_to_center * radius, center_point.y() + dy / dist_to_center * radius
            )
        return ((hover_point, center_point),)

    def _snap_point(self, view_pos: qc.QPoint, raw_scene_point: qc.QPointF) -> Tuple[qc.QPointF, bool]:
        """"Aim assist": if an existing POINT, LINE endpoint, or CIRCLE is
        within `_SNAP_TOLERANCE_PX` screen pixels of `view_pos`, snaps to
        its exact coordinate (a CIRCLE's true centre, even though what's in
        reach of the cursor is its rendered ring) — same idea as AutoCAD's
        ENDPOINT/NODE/CENTER object snap. Returns (point_to_use, whether it
        was actually snapped)."""
        rect = qc.QRect(
            view_pos.x() - _SNAP_TOLERANCE_PX,
            view_pos.y() - _SNAP_TOLERANCE_PX,
            _SNAP_TOLERANCE_PX * 2,
            _SNAP_TOLERANCE_PX * 2,
        )
        best_point: Optional[qc.QPointF] = None
        best_distance = float(_SNAP_TOLERANCE_PX)
        for item in self.items(rect):
            if item.data(_HANDLE_ROLE) is None:
                continue  # preview/marker items aren't real entities - never snap to them
            for hover_point, snap_point in self._snap_candidates_for(item, raw_scene_point):
                device_point = self.mapFromScene(hover_point)
                distance = math.hypot(device_point.x() - view_pos.x(), device_point.y() - view_pos.y())
                if distance < best_distance:
                    best_distance = distance
                    best_point = snap_point
        if best_point is not None:
            return best_point, True
        return raw_scene_point, False

    def _set_snap_indicator(self, point: Optional[qc.QPointF]) -> None:
        # Painted in drawForeground (see below) rather than kept as a real
        # QGraphicsItem in the scene: a document edit swaps in a whole new
        # QGraphicsScene on every change (see DxfViewer._render), and an
        # item recreated/re-added to a scene right after such a swap has
        # caused a hard crash here — the same risk-free approach the
        # selection highlight below already uses.
        if self._snap_indicator == point:
            return
        self._snap_indicator = point
        self.viewport().update()

    def set_selected_item(self, item: Optional[qw.QGraphicsItem]) -> None:
        """Convenience for a single-item (or empty) selection."""
        self.set_selected_items([item] if item is not None else [])

    def set_selected_items(self, items: List[qw.QGraphicsItem]) -> None:
        self._selected_items = list(items)
        self.viewport().update()

    def _toggle_selected_item(self, item: Optional[qw.QGraphicsItem]) -> None:
        if item is None:
            return
        if item in self._selected_items:
            self._selected_items.remove(item)
        else:
            self._selected_items.append(item)
        self.viewport().update()

    def _emit_selection(self) -> None:
        handles = [item.data(_HANDLE_ROLE) for item in self._selected_items]
        self.entitySelected.emit(handles)

    def mousePressEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        if event.button() == qc.Qt.MouseButton.MiddleButton:
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(qc.Qt.CursorShape.ClosedHandCursor)
            return
        self._press_pos = event.position().toPoint()
        self._drag_candidate = None
        if self._tool is None and event.button() == qc.Qt.MouseButton.LeftButton:
            # Remembered so a later drag (see mouseMoveEvent) can move
            # whatever was actually pressed on, without re-hit-testing at a
            # possibly-different position once the drag is under way.
            self._drag_candidate = self._topmost_handled_item(self._press_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        if self._pan_last_pos is not None:
            # Reuses pan_by()/centerOn() (scene-space, same as the PAN
            # command) rather than nudging scrollbar values directly —
            # scrollbars have no range to move within right after
            # fit_to_scene() sets a tightly-fit sceneRect, which would make
            # a raw scrollbar-based drag silently do nothing at that zoom.
            pos = event.position().toPoint()
            old_scene = self.mapToScene(self._pan_last_pos)
            new_scene = self.mapToScene(pos)
            self._pan_last_pos = pos
            self.pan_by(old_scene.x() - new_scene.x(), old_scene.y() - new_scene.y())
            return
        super().mouseMoveEvent(event)
        if self._tool is not None:
            view_pos = event.position().toPoint()
            raw_point = self.mapToScene(view_pos)
            point, snapped = self._snap_point(view_pos, raw_point)
            self._set_snap_indicator(point if snapped else None)
            self._tool.update_preview((point.x(), point.y()), self.scene())
        elif self._press_pos is not None:
            view_pos = event.position().toPoint()
            moved = (view_pos - self._press_pos).manhattanLength()
            if moved <= _CLICK_THRESHOLD_PX:
                return
            if self._drag_candidate is not None:
                self._ensure_dragging_items(view_pos)
            else:
                self._update_rubber_band(view_pos)

    def _ensure_dragging_items(self, view_pos: qc.QPoint) -> None:
        """Live-previews a click-and-drag move: the first call (once the
        drag clears the click threshold) picks which items follow the
        cursor — the whole current selection if the press landed on a
        member of it, otherwise just the pressed item, which also becomes
        the new selection (matching AutoCAD's press-and-drag-to-move)."""
        if not self._dragging_items:
            self._dragging_items = True
            if self._drag_candidate in self._selected_items:
                self._drag_items = list(self._selected_items)
            else:
                self._drag_items = [self._drag_candidate]
                self.set_selected_items(self._drag_items)
                self._emit_selection()
            self._drag_start_scene = self.mapToScene(self._press_pos)
        assert self._drag_start_scene is not None
        current_scene = self.mapToScene(view_pos)
        dx = current_scene.x() - self._drag_start_scene.x()
        dy = current_scene.y() - self._drag_start_scene.y()
        for item in self._drag_items:
            item.setPos(dx, dy)

    def mouseReleaseEvent(self, event: qg.QMouseEvent) -> None:  # noqa: N802
        if event.button() == qc.Qt.MouseButton.MiddleButton:
            self._pan_last_pos = None
            self.setCursor(qc.Qt.CursorShape.CrossCursor if self._tool is not None else qc.Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)
        if event.button() != qc.Qt.MouseButton.LeftButton or self._press_pos is None:
            return
        press_pos = self._press_pos
        release_pos = event.position().toPoint()
        self._press_pos = None
        if self._tool is not None:
            # A tool is active: no drag/pan is possible here (DragMode is
            # always NoDrag), so every release places a point — no distance
            # check, which is exactly what previously discarded a slightly
            # unsteady click while drawing as "a pan drag, not a click".
            raw_point = self.mapToScene(release_pos)
            scene_point, _ = self._snap_point(release_pos, raw_point)
            self._tool.on_click((scene_point.x(), scene_point.y()))
            self.toolPointPlaced.emit()
            return
        if self._dragging_items:
            self._finish_drag_items(release_pos)
            return
        shift = bool(event.modifiers() & qc.Qt.KeyboardModifier.ShiftModifier)
        moved = (release_pos - press_pos).manhattanLength()
        if moved > _CLICK_THRESHOLD_PX:
            self._finish_rubber_band(press_pos, release_pos, additive=shift)
            return
        item = self._topmost_handled_item(release_pos)
        if shift:
            self._toggle_selected_item(item)
        else:
            self.set_selected_items([item] if item is not None else [])
        self._emit_selection()

    def _finish_drag_items(self, release_pos: qc.QPoint) -> None:
        assert self._drag_start_scene is not None
        current_scene = self.mapToScene(release_pos)
        dx = current_scene.x() - self._drag_start_scene.x()
        dy = current_scene.y() - self._drag_start_scene.y()
        handles = [item.data(_HANDLE_ROLE) for item in self._drag_items]
        for item in self._drag_items:
            # The real move is committed as a Command below and applied via
            # a full re-render — this per-item offset was only ever a live
            # preview, so it's undone rather than left to fight the redraw.
            item.setPos(0, 0)
        self._dragging_items = False
        self._drag_items = []
        self._drag_candidate = None
        self._drag_start_scene = None
        if handles and (abs(dx) > 1e-9 or abs(dy) > 1e-9):
            self.itemsDragMoved.emit(handles, dx, dy)

    def _update_rubber_band(self, current_pos: qc.QPoint) -> None:
        if self._press_pos is None:
            return
        if self._rubber_band is None:
            self._rubber_band = qw.QRubberBand(qw.QRubberBand.Shape.Rectangle, self.viewport())
        self._rubber_band.setGeometry(qc.QRect(self._press_pos, current_pos).normalized())
        self._rubber_band.show()

    def _finish_rubber_band(self, press_pos: qc.QPoint, release_pos: qc.QPoint, additive: bool) -> None:
        if self._rubber_band is not None:
            self._rubber_band.hide()
        rect = qc.QRect(press_pos, release_pos).normalized()
        found = self._items_in_rect(rect)
        if additive:
            merged = list(self._selected_items)
            for item in found:
                if item not in merged:
                    merged.append(item)
            self.set_selected_items(merged)
        else:
            self.set_selected_items(found)
        self._emit_selection()

    def _items_in_rect(self, rect: qc.QRect) -> List[qw.QGraphicsItem]:
        return [item for item in self.items(rect) if item.data(_HANDLE_ROLE) is not None]

    def _topmost_handled_item(self, view_pos: qc.QPoint) -> Optional[qw.QGraphicsItem]:
        # A few-pixel tolerance box, in device space, so it stays easy to hit
        # a POINT or a thin line regardless of the current zoom level. Among
        # everything the box overlaps, picks whichever is *actually closest*
        # to the click — not just whichever Qt's z-order-based items()
        # happens to return first. A line's own shape() is inflated by its
        # (cosmetic, i.e. meant to be device-pixel) pen width applied as
        # scene units, so without this an inflated-but-farther item could
        # permanently shadow a genuinely closer one every time they overlap.
        tolerance = 4
        rect = qc.QRect(view_pos.x() - tolerance, view_pos.y() - tolerance, tolerance * 2, tolerance * 2)
        click_scene = self.mapToScene(view_pos)
        best_item: Optional[qw.QGraphicsItem] = None
        best_distance = math.inf
        for item in self.items(rect):
            if item.data(_HANDLE_ROLE) is None:
                continue
            distance = _distance_to_item(click_scene, item)
            if distance < best_distance:
                best_distance = distance
                best_item = item
        return best_item

    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:  # noqa: N802
        scale = _x_scale(painter.transform()) or 1.0
        color = qg.QColor(UiColor.ACCENT)

        if self._snap_indicator is not None:
            self._paint_snap_indicator(painter, self._snap_indicator, scale, color)

        # Retraces every *actual* selected entity in a bright, constant-width
        # accent stroke — same idea as AutoCAD's selection highlight — rather
        # than washing a translucent tint over its whole bounding box (which,
        # e.g. for a diagonal line, mostly highlights empty space around it).
        if not self._selected_items:
            return
        pen = qg.QPen(color, 3)
        pen.setCosmetic(True)
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        for item in self._selected_items:
            if isinstance(item, _PointItem):
                radius = item._radius / scale + 3 / scale
                painter.drawEllipse(item._pos, radius, radius)
            elif isinstance(item, qw.QGraphicsLineItem):
                painter.drawLine(item.line())
            elif isinstance(item, qw.QGraphicsPathItem):
                painter.drawPath(item.path())
            elif isinstance(item, qw.QGraphicsPolygonItem):
                painter.drawPolygon(item.polygon())
            else:
                fill_color = qg.QColor(color)
                fill_color.setAlpha(90)
                painter.fillRect(item.sceneTransform().mapRect(item.boundingRect()), fill_color)

    @staticmethod
    def _paint_snap_indicator(painter: qg.QPainter, point: qc.QPointF, scale: float, color: qg.QColor) -> None:
        """A small constant-size square around a snapped-to point/endpoint —
        the "aim assist" feedback for LINE/POINT/CIRCLE/MOVE, drawn the same
        risk-free way as the selection highlight above (see
        `_set_snap_indicator`)."""
        pen = qg.QPen(color, 1.6)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        half = 4.5 / scale
        painter.drawRect(qc.QRectF(point.x() - half, point.y() - half, half * 2, half * 2))


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


def _offset_segment_perpendicular(
    start: Tuple[float, float], end: Tuple[float, float], offset: float
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """`start`/`end` shifted sideways by `offset`, perpendicular to the
    segment's own direction — the same "two parallel lines" convention as
    core.geometry.offset_segment_perpendicular (used for the batch-generated
    pipe), reimplemented here on plain (x, y) tuples since interactive
    drawing in this module is 2D-only and doesn't otherwise touch
    core.geometry/models.Point. A zero-length segment has no defined
    direction, so it's returned unshifted."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        return start, end
    ux, uy = -dy / length, dx / length
    shift = (ux * offset, uy * offset)
    return (start[0] + shift[0], start[1] + shift[1]), (end[0] + shift[0], end[1] + shift[1])


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

    def build_command(self, layer: str) -> EditCommand:
        """`layer` is the document's current active layer — new-entity tools
        draw onto it; tools that don't create anything (Move) ignore it."""
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

    def build_command(self, layer: str) -> EditCommand:
        assert self._point is not None
        return AddPointCommand(self._point, layer)


_DEFAULT_TEXT_HEIGHT = 0.6


class TextToolSession(ToolSession):
    """AutoCAD's TEXT command, simplified to one shot: click (or type) an
    insertion point, then type the string itself — committed as soon as
    that text is entered, rather than staying in a live on-canvas edit."""

    def __init__(self, height: float = _DEFAULT_TEXT_HEIGHT) -> None:
        super().__init__()
        self.prompt = "Specify text insertion point: "
        self._insert: Optional[Tuple[float, float]] = None
        self._text: Optional[str] = None
        self._height = height

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._insert is None:
            self._insert = point
            self.prompt = "Enter text: "
        # A stray click once only the text content is left to fill in has
        # nothing to do — that step only accepts typed input (see on_text).

    def on_text(self, text: str) -> Optional[str]:
        if self._insert is None:
            coord = _parse_coordinate(text, last_point=None)
            if coord is None:
                return f'Point must be given as "x,y": "{text}".'
            self._insert = coord
            self.prompt = "Enter text: "
            return None
        if not text.strip():
            return "Text cannot be empty."
        self._text = text
        return None

    def is_done(self) -> bool:
        return self._insert is not None and self._text is not None

    def build_command(self, layer: str) -> EditCommand:
        assert self._insert is not None and self._text is not None
        return AddTextCommand(self._text, self._insert, self._height, layer)


class LineToolSession(ToolSession):
    """AutoCAD's LINE command chains: finishing one segment doesn't exit the
    command, it immediately prompts for the next point starting from where
    the last one ended — see `continuation()`, used by DxfViewer to keep
    this tool active instead of dropping back to Select after every click."""

    def __init__(self, start: Optional[Tuple[float, float]] = None) -> None:
        super().__init__()
        self.prompt = "Specify next point: " if start is not None else "Specify first point: "
        self._start: Optional[Tuple[float, float]] = start
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

    def build_command(self, layer: str) -> EditCommand:
        assert self._start is not None and self._end is not None
        return AddLineCommand(self._start, self._end, layer)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None

    def continuation(self) -> "LineToolSession":
        """A fresh LineToolSession picking up where this one left off, so
        drawing a connected polyline-like run is just click, click, click —
        no need to reselect the Line tool for every segment."""
        assert self._end is not None
        return LineToolSession(start=self._end)


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

    def build_command(self, layer: str) -> EditCommand:
        assert self._center is not None and self._radius is not None
        return AddCircleCommand(self._center, self._radius, layer)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None


class PipeToolSession(ToolSession):
    """A protective casing pipe (RURA OSŁONOWA), drawn as two parallel LINE
    entities straddling the segment — the same "two lines" convention as
    core.commands.survey.build_pipe_command. Chains like LINE: finishing a
    segment immediately starts the next one from its endpoint, reusing the
    same width, so a multi-segment pipe run is click, click, click, ...
    (each new segment needs only its endpoint, not a fresh width)."""

    def __init__(
        self, start: Optional[Tuple[float, float]] = None, width: Optional[float] = None
    ) -> None:
        super().__init__()
        self.prompt = "Specify next point: " if start is not None else "Specify first point: "
        self._start: Optional[Tuple[float, float]] = start
        self._end: Optional[Tuple[float, float]] = None
        self._width: Optional[float] = width
        self._preview_items: List[qw.QGraphicsLineItem] = []

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._start is None:
            self._start = point
            self.prompt = "Specify next point: "
        elif self._end is None:
            self._end = point
            if self._width is None:
                self.prompt = "Specify pipe width (or a point): "
        elif self._width is None:
            width = _distance(self._end, point)
            if width > 0:
                self._width = width

    def on_text(self, text: str) -> Optional[str]:
        if self._start is None:
            coord = _parse_coordinate(text, last_point=None)
            if coord is None:
                return f'Point must be given as "x,y": "{text}".'
            self._start = coord
            self.prompt = "Specify next point: "
            return None
        if self._end is None:
            coord = _parse_coordinate(text, last_point=self._start)
            if coord is None:
                return f'Point must be given as "x,y" or "@dx,dy": "{text}".'
            self._end = coord
            if self._width is None:
                self.prompt = "Specify pipe width (or a point): "
            return None
        try:
            width = float(text.strip())
        except ValueError:
            coord = _parse_coordinate(text, last_point=self._end)
            if coord is None:
                return f'Requires a numeric width or a point: "{text}".'
            width = _distance(self._end, coord)
        if width <= 0:
            return "Width must be positive."
        self._width = width
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._start is None:
            return
        if self._end is None:
            self._set_preview_segments(scene, [(self._start, point)])
            return
        if self._width is not None:
            return  # nothing left to preview - width already known (or continuation started with one)
        width = _distance(self._end, point)
        if width <= 0:
            self._set_preview_segments(scene, [])
            return
        half = width / 2.0
        self._set_preview_segments(
            scene,
            [
                _offset_segment_perpendicular(self._start, self._end, half),
                _offset_segment_perpendicular(self._start, self._end, -half),
            ],
        )

    def _set_preview_segments(
        self, scene: qw.QGraphicsScene, segments: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    ) -> None:
        while len(self._preview_items) < len(segments):
            item = qw.QGraphicsLineItem()
            item.setPen(_preview_pen())
            scene.addItem(item)
            self._preview_items.append(item)
        while len(self._preview_items) > len(segments):
            scene.removeItem(self._preview_items.pop())
        for item, (a, b) in zip(self._preview_items, segments):
            item.setLine(a[0], a[1], b[0], b[1])

    def is_done(self) -> bool:
        return self._start is not None and self._end is not None and self._width is not None

    def build_command(self, layer: str) -> EditCommand:
        assert self._start is not None and self._end is not None and self._width is not None
        half = self._width / 2.0
        line_a = _offset_segment_perpendicular(self._start, self._end, half)
        line_b = _offset_segment_perpendicular(self._start, self._end, -half)
        return CompositeCommand(
            [AddLineCommand(line_a[0], line_a[1], layer), AddLineCommand(line_b[0], line_b[1], layer)]
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def continuation(self) -> "PipeToolSession":
        """A fresh PipeToolSession picking up where this one left off, same
        width — so a multi-segment pipe run needs only one click per
        endpoint after the first segment, not a width prompt every time."""
        assert self._end is not None and self._width is not None
        return PipeToolSession(start=self._end, width=self._width)


class MoveToolSession(ToolSession):
    """Select objects first, then this tool moves them: click/type a base
    point, then a destination — same as AutoCAD's MOVE. Ignores `layer` in
    build_command (moving doesn't create anything new)."""

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = "Specify base point: "
        self._base: Optional[Tuple[float, float]] = None
        self._dest: Optional[Tuple[float, float]] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = "Specify second point: "
        else:
            self._dest = point

    def on_text(self, text: str) -> Optional[str]:
        coord = _parse_coordinate(text, last_point=self._base)
        if coord is None:
            return f'Point must be given as "x,y" or "@dx,dy": "{text}".'
        if self._base is None:
            self._base = coord
            self.prompt = "Specify second point: "
        else:
            self._dest = coord
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._dest is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(_preview_pen())
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

    def is_done(self) -> bool:
        return self._base is not None and self._dest is not None

    def build_command(self, layer: str) -> EditCommand:
        assert self._base is not None and self._dest is not None
        dx = self._dest[0] - self._base[0]
        dy = self._dest[1] - self._base[1]
        return MoveCommand(self._handles, dx, dy)

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
        self._input.setPlaceholderText("POINT, TEXT, LINE, CIRCLE, PIPE, ZOOM …")
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
        self._echo("Type POINT, TEXT, LINE, CIRCLE, PIPE, ERASE, U(ndo), REDO, ZOOM, PAN or REGEN.")

    def show_response(self, message: str) -> None:
        if message:
            self._echo(message)

    def set_placeholder(self, text: str) -> None:
        self._input.setPlaceholderText(text)

    def focus_input(self) -> None:
        """Moves keyboard focus to the Command: field — called whenever an
        active tool's next step needs typed input (e.g. TEXT's content),
        so the user can start typing right away instead of having to click
        into this field first."""
        self._input.setFocus()

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


class TextOptionsBar(qw.QFrame):
    """Floating panel above a selected TEXT entity, in AutoCAD's in-place
    text editor spirit — but scoped to what a plain single-line DXF TEXT
    actually has: content, height, rotation, color. No MTEXT-style
    per-character bold/italic/underline, since a single-line TEXT has no
    such formatting to carry.

    Pure UI like LayerPanel: each field commits as a plain-value signal
    once its value actually changes, and DxfViewer turns that into the
    matching core.commands.text Command."""

    contentChanged = qc.pyqtSignal(str, str)  # handle, new text
    heightChanged = qc.pyqtSignal(str, float)  # handle, new height
    rotationChanged = qc.pyqtSignal(str, float)  # handle, new rotation (degrees)
    colorChanged = qc.pyqtSignal(str, tuple)  # handle, new rgb

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("textOptionsBar")
        self.handle: Optional[str] = None
        self._orig_text = ""
        self._orig_height = 0.0
        self._orig_rotation = 0.0
        self.hide()

        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        layout.setSpacing(SPACE_XS)

        self._content = qw.QLineEdit()
        self._content.setObjectName("textOptionsContent")
        self._content.setFixedWidth(150)
        self._content.setToolTip("Text content")
        self._content.editingFinished.connect(self._emit_content)
        layout.addWidget(self._content)

        self._height = qw.QLineEdit()
        self._height.setObjectName("textOptionsField")
        self._height.setFixedWidth(54)
        self._height.setToolTip("Text height")
        self._height.setValidator(decimal_validator(0.001, 9999.0, 3))
        self._height.editingFinished.connect(self._emit_height)
        layout.addWidget(self._height)

        self._rotation = qw.QLineEdit()
        self._rotation.setObjectName("textOptionsField")
        self._rotation.setFixedWidth(54)
        self._rotation.setToolTip("Rotation (degrees)")
        self._rotation.setValidator(decimal_validator(-360.0, 360.0, 2))
        self._rotation.editingFinished.connect(self._emit_rotation)
        layout.addWidget(self._rotation)

        self._color = ColorSwatchButton((255, 255, 255), "Text color")
        self._color.colorChanged.connect(self._emit_color)
        layout.addWidget(self._color)

    def bind(self, handle: str, text: str, height: float, rotation: float, rgb: Tuple[int, int, int]) -> None:
        """Points this bar at one TEXT entity and fills it with that
        entity's current values — called by DxfViewer.sync_text_options_bar
        every time the selection or the document changes."""
        self.handle = handle
        self._orig_text, self._orig_height, self._orig_rotation = text, height, rotation
        self._content.setText(text)
        self._height.setText(f"{height:g}")
        self._rotation.setText(f"{rotation:g}")
        self._color.set_color(rgb)
        self.show()
        self.adjustSize()

    def _emit_content(self) -> None:
        text = self._content.text()
        if self.handle and text and text != self._orig_text:
            self.contentChanged.emit(self.handle, text)

    def _emit_height(self) -> None:
        text = self._height.text()
        if not self.handle or not text:
            return
        height = float(text.replace(",", "."))
        if height > 0 and height != self._orig_height:
            self.heightChanged.emit(self.handle, height)

    def _emit_rotation(self) -> None:
        text = self._rotation.text()
        if not self.handle or not text:
            return
        rotation = float(text.replace(",", "."))
        if rotation != self._orig_rotation:
            self.rotationChanged.emit(self.handle, rotation)

    def _emit_color(self, rgb: Tuple[int, int, int]) -> None:
        if self.handle:
            self.colorChanged.emit(self.handle, rgb)


class _CommandError(Exception):
    """Raised by a command handler for a malformed argument; the message is
    shown in the command line, same as an invalid AutoCAD command prompt."""


class DxfCommandInterpreter:
    """Parses a small set of AutoCAD-style commands: view control
    (ZOOM/PAN/REGEN, applied directly to the CadGraphicsView) and editing
    (POINT/TEXT/LINE/CIRCLE/PIPE/MOVE/ERASE/UNDO/REDO, applied through the
    owning DxfViewer's DXFDocument + CommandHistory)."""

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
            "TEXT": self._cmd_text,
            "T": self._cmd_text,
            "LINE": self._cmd_line,
            "L": self._cmd_line,
            "CIRCLE": self._cmd_circle,
            "C": self._cmd_circle,
            "PIPE": self._cmd_pipe,
            "RURA": self._cmd_pipe,
            "RU": self._cmd_pipe,
            "MOVE": self._cmd_move,
            "M": self._cmd_move,
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
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddPointCommand(coord, doc.active_layer))
            return ""
        self._viewer.start_tool(PointToolSession())
        return ""

    def _cmd_text(self, args: List[str]) -> str:
        # No direct-args form (unlike POINT/LINE/CIRCLE/PIPE): the text
        # content itself can contain spaces, which this command line's
        # naive whitespace split can't round-trip — always interactive.
        self._viewer.start_tool(TextToolSession())
        return ""

    def _cmd_line(self, args: List[str]) -> str:
        if len(args) >= 2:
            start = _parse_coordinate(args[0], last_point=None)
            end = _parse_coordinate(args[1], last_point=start)
            if start is None or end is None:
                raise _CommandError(f'Points must be given as "x,y": "{args[0]} {args[1]}".')
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddLineCommand(start, end, doc.active_layer))
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
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddCircleCommand(center, radius, doc.active_layer))
            return ""
        self._viewer.start_tool(CircleToolSession())
        return ""

    def _cmd_pipe(self, args: List[str]) -> str:
        if len(args) >= 3:
            start = _parse_coordinate(args[0], last_point=None)
            end = _parse_coordinate(args[1], last_point=start)
            if start is None or end is None:
                raise _CommandError(f'Points must be given as "x,y": "{args[0]} {args[1]}".')
            try:
                width = float(args[2])
            except ValueError:
                raise _CommandError(f'Requires a numeric width: "{args[2]}".') from None
            if width <= 0:
                raise _CommandError("Width must be positive.")
            doc = self._viewer.ensure_document()
            half = width / 2.0
            line_a = _offset_segment_perpendicular(start, end, half)
            line_b = _offset_segment_perpendicular(start, end, -half)
            self._viewer.execute_command(
                CompositeCommand(
                    [
                        AddLineCommand(line_a[0], line_a[1], doc.active_layer),
                        AddLineCommand(line_b[0], line_b[1], doc.active_layer),
                    ]
                )
            )
            return ""
        self._viewer.start_tool(PipeToolSession())
        return ""

    def _cmd_move(self, args: List[str]) -> str:
        self._viewer.start_move_tool()
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


class DxfToolbar(qw.QWidget):
    """Icon toolbar docked above the DXF preview — one-click access to the
    same draw/edit/view actions the command line already exposes (undo/redo
    live in MainWindow's own Edit menu instead, not here). Kept in sync
    with the command line either way: typing "LINE" highlights the Line
    button exactly as clicking it would, since both paths go through
    DxfViewer.start_tool()/cancel_tool()."""

    pointRequested = qc.pyqtSignal()
    textRequested = qc.pyqtSignal()
    lineRequested = qc.pyqtSignal()
    circleRequested = qc.pyqtSignal()
    pipeRequested = qc.pyqtSignal()
    selectRequested = qc.pyqtSignal()
    moveRequested = qc.pyqtSignal()
    eraseRequested = qc.pyqtSignal()
    zoomExtentsRequested = qc.pyqtSignal()
    zoomInRequested = qc.pyqtSignal()
    zoomOutRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dxfToolbar")
        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        self._tool_buttons: Dict[str, qw.QToolButton] = {}
        self._tool_signals = {
            "point": self.pointRequested,
            "text": self.textRequested,
            "line": self.lineRequested,
            "circle": self.circleRequested,
            "pipe": self.pipeRequested,
            "move": self.moveRequested,
        }

        self._add_tool_button(layout, "select", "↖", "Select / cancel current tool (Esc)")
        self._add_tool_button(layout, "point", "•", "Point (PO)")
        self._add_tool_button(layout, "text", "A", "Text (T)")
        self._add_tool_button(layout, "line", "╱", "Line (L)")
        self._add_tool_button(layout, "circle", "○", "Circle (C)")
        self._add_tool_button(layout, "pipe", "∥", "Pipe (RURA)")
        layout.addWidget(self._separator())
        self._add_tool_button(layout, "move", "✥", "Move selected (M)")
        self._erase_btn = self._add_plain_button(layout, "✕", "Erase selected (Del)", self.eraseRequested)
        layout.addWidget(self._separator())
        self._add_plain_button(layout, "⤢", "Zoom Extents (ZOOM E)", self.zoomExtentsRequested)
        self._add_plain_button(layout, "+", "Zoom In", self.zoomInRequested)
        self._add_plain_button(layout, "−", "Zoom Out", self.zoomOutRequested)
        layout.addStretch(1)

        self._active_key = "select"
        self._tool_buttons["select"].setChecked(True)
        self._erase_btn.setEnabled(False)

    def _add_tool_button(self, layout: qw.QHBoxLayout, key: str, glyph: str, tooltip: str) -> None:
        btn = qw.QToolButton()
        btn.setObjectName("dxfToolBtn")
        btn.setText(glyph)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked, k=key: self._on_tool_clicked(k, checked))
        layout.addWidget(btn)
        self._tool_buttons[key] = btn

    @staticmethod
    def _add_plain_button(
        layout: qw.QHBoxLayout, glyph: str, tooltip: str, signal: qc.pyqtBoundSignal
    ) -> qw.QToolButton:
        btn = qw.QToolButton()
        btn.setObjectName("dxfToolBtn")
        btn.setText(glyph)
        btn.setToolTip(tooltip)
        btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(signal.emit)
        layout.addWidget(btn)
        return btn

    @staticmethod
    def _separator() -> qw.QFrame:
        line = qw.QFrame()
        line.setObjectName("dxfToolbarSeparator")
        line.setFrameShape(qw.QFrame.Shape.VLine)
        return line

    def _on_tool_clicked(self, key: str, checked: bool) -> None:
        # A tool button behaves like a toggle: click it to start that tool,
        # click the *active* one again (checked -> unchecked) to cancel back
        # to plain selection — same as clicking Select or pressing Esc.
        if key == "select":
            self.selectRequested.emit()
        elif checked:
            self._tool_signals[key].emit()
        else:
            self.selectRequested.emit()

    def set_active_tool(self, key: Optional[str]) -> None:
        self._active_key = key or "select"
        for name, btn in self._tool_buttons.items():
            btn.setChecked(name == self._active_key)

    def set_erase_enabled(self, enabled: bool) -> None:
        self._erase_btn.setEnabled(enabled)


_TOOL_KEYS = {
    PointToolSession: "point",
    TextToolSession: "text",
    LineToolSession: "line",
    CircleToolSession: "circle",
    PipeToolSession: "pipe",
    MoveToolSession: "move",
}


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
        self._selected_handles: List[str] = []
        # Snapshot of layer names as of the last DXF *import* (load_file) —
        # None for a blank/new drawing, where "prune to core layers" has
        # nothing to work from. Layers created afterward (Add Layer, or by
        # drawing) are never in this set, so the prune action never touches
        # them regardless of their name — see core.commands.layers.layers_to_prune.
        self._imported_layer_names: Optional[set] = None

        outer = qw.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE_SM)

        canvas_column = qw.QWidget()
        layout = qw.QVBoxLayout(canvas_column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        # Docked above the empty-state / canvas stack, so it's usable even
        # before any drawing exists — clicking a draw tool auto-creates a
        # blank DXF the same way typing e.g. "LINE" already does.
        self._toolbar = DxfToolbar()
        layout.addWidget(self._toolbar)

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
        self._view.itemsDragMoved.connect(self._on_items_drag_moved)
        self._view.viewportChanged.connect(self._reposition_text_options_bar)
        self._text_options_bar = TextOptionsBar(self)
        self._text_options_bar.contentChanged.connect(self._on_text_content_changed)
        self._text_options_bar.heightChanged.connect(self._on_text_height_changed)
        self._text_options_bar.rotationChanged.connect(self._on_text_rotation_changed)
        self._text_options_bar.colorChanged.connect(self._on_text_color_changed)
        self._command_line = CommandLine()
        self._command_line.commandEntered.connect(self._on_command_entered)
        self._command_line.undoRequested.connect(lambda: self._echo(self.undo()))
        self._command_line.redoRequested.connect(lambda: self._echo(self.redo()))
        canvas_layout.addWidget(self._view, 1)
        canvas_layout.addWidget(self._command_line)

        self._interpreter = DxfCommandInterpreter(self)

        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._canvas_page)

        outer.addWidget(canvas_column, 1)
        # Not added to this widget's own layout — main_window.py docks it
        # into the left column's "Layers" navigation item instead, via the
        # layer_panel property below. Constructed and wired here regardless,
        # since all its signals route through this class's own commands.
        self._layer_panel = LayerPanel()

        self._toolbar.pointRequested.connect(lambda: self._start_draw_tool(PointToolSession))
        self._toolbar.textRequested.connect(lambda: self._start_draw_tool(TextToolSession))
        self._toolbar.lineRequested.connect(lambda: self._start_draw_tool(LineToolSession))
        self._toolbar.circleRequested.connect(lambda: self._start_draw_tool(CircleToolSession))
        self._toolbar.pipeRequested.connect(lambda: self._start_draw_tool(PipeToolSession))
        self._toolbar.selectRequested.connect(self.cancel_tool)
        self._toolbar.moveRequested.connect(self.start_move_tool)
        self._toolbar.eraseRequested.connect(lambda: self._echo(self.delete_selected()))
        self._toolbar.zoomExtentsRequested.connect(self._view.fit_to_scene)
        self._toolbar.zoomInRequested.connect(lambda: self._view.zoom_by(1.25))
        self._toolbar.zoomOutRequested.connect(lambda: self._view.zoom_by(0.8))

        self._layer_panel.addLayerRequested.connect(self._on_add_layer)
        self._layer_panel.deleteLayerRequested.connect(lambda n: self.execute_command(DeleteLayerCommand(n)))
        self._layer_panel.colorChangeRequested.connect(
            lambda n, rgb: self.execute_command(SetLayerColorCommand(n, rgb))
        )
        self._layer_panel.visibilityToggled.connect(
            lambda n, v: self.execute_command(SetLayerVisibleCommand(n, v))
        )
        self._layer_panel.setActiveRequested.connect(
            lambda n: self.execute_command(SetActiveLayerCommand(n))
        )
        self._layer_panel.selectLayerRequested.connect(self.select_by_layer)
        self._layer_panel.pruneLayersRequested.connect(self._on_prune_layers)

        # Undo/redo are window-scoped: they should work no matter which
        # widget in the main window currently has focus (a config field in
        # the left panel, a button, ...), not just while the DXF panel
        # itself is focused. Delete/Esc stay panel-scoped on purpose — they'd
        # otherwise fire while e.g. editing an unrelated text field.
        self._add_shortcut(
            "Ctrl+Z", lambda: self._echo(self.undo()), context=qc.Qt.ShortcutContext.WindowShortcut
        )
        self._add_shortcut(
            "Ctrl+Y", lambda: self._echo(self.redo()), context=qc.Qt.ShortcutContext.WindowShortcut
        )
        self._add_shortcut("Delete", lambda: self._echo(self.delete_selected()))
        self._add_shortcut("Esc", self.cancel_tool)

    def _add_shortcut(
        self,
        sequence: str,
        slot,
        context: qc.Qt.ShortcutContext = qc.Qt.ShortcutContext.WidgetWithChildrenShortcut,
    ) -> None:
        shortcut = qg.QShortcut(qg.QKeySequence(sequence), self)
        shortcut.setContext(context)
        shortcut.activated.connect(slot)

    @property
    def view(self) -> CadGraphicsView:
        return self._view

    @property
    def has_document(self) -> bool:
        return self._doc is not None

    @property
    def layer_panel(self) -> LayerPanel:
        """The layers list widget — owned and wired up here, but docked
        into main_window.py's left column rather than laid out in `self`."""
        return self._layer_panel

    def save_document(self, file_path: str) -> None:
        assert self._doc is not None
        self._doc.save(file_path)

    def ensure_document(self) -> DXFDocument:
        """Returns the current document, creating a blank one first if none
        is loaded yet — so drawing commands always have somewhere to go."""
        if self._doc is None:
            self._doc = DXFDocument.new()
            self._history = CommandHistory()
            self._selected_handles = []
            self._render(preserve_view=False)
            self._command_line.reset()
            self._stack.setCurrentWidget(self._canvas_page)
        return self._doc

    def show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty_page)

    def clear(self) -> None:
        self.cancel_tool()
        self._view.scene().clear()
        self._view.set_selected_items([])
        self.entity_count = 0
        self.layer_count = 0
        self._doc = None
        self._view.set_document(None)
        self._history = None
        self._selected_handles = []
        self._imported_layer_names = None
        self._layer_panel.refresh([])
        self._layer_panel.set_prune_available(False)
        self.show_empty()

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """Loads and renders `file_path`. Returns (success, error_message)."""
        try:
            doc = DXFDocument.load(file_path)
        except IOError as exc:
            return False, f"Could not read file: {exc}"
        except ezdxf.DXFError as exc:
            return False, f"Not a valid DXF file: {exc}"
        return self._adopt_document(doc)

    def load_from_text(self, content: str) -> Tuple[bool, str]:
        """Loads and renders a document from embedded DXF text rather than a
        file path — the counterpart to load_file(), used to restore a saved
        project's embedded DXF snapshot (see core.project) so a project
        doesn't lose in-progress DXF edits that were never separately saved
        to their own .dxf file."""
        try:
            doc = DXFDocument.from_text(content)
        except ezdxf.DXFError as exc:
            return False, f"Could not restore the project's DXF snapshot: {exc}"
        return self._adopt_document(doc)

    def to_dxf_text(self) -> Optional[str]:
        """The current document's DXF content as plain text, or None if no
        document is loaded — for embedding in a saved project (see
        core.project, ui.main_window)."""
        if self._doc is None:
            return None
        return self._doc.to_text()

    def _adopt_document(self, doc: DXFDocument) -> Tuple[bool, str]:
        """Makes `doc` the current document and renders it — shared by
        load_file() and load_from_text(), which differ only in how they
        obtain the DXFDocument itself."""
        self._doc = doc
        self._history = CommandHistory()
        self._selected_handles = []
        # Captured before any further edit, so "prune to core layers" always
        # has the exact set of layers this file actually arrived with —
        # never anything added afterward, even in this same session.
        self._imported_layer_names = {info.name for info in doc.iter_layers()}
        try:
            self._render(preserve_view=False)
        except Exception as exc:  # noqa: BLE001 - a bad/unsupported drawing must never crash the app
            self._doc = None
            self._view.set_document(None)
            self._history = None
            self._imported_layer_names = None
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
        if not self._selected_handles:
            return "Select an object first."
        self.execute_command(DeleteEntityCommand(self._selected_handles))
        self.clear_selection()
        return ""

    def clear_selection(self) -> None:
        self._selected_handles = []
        self._view.set_selected_items([])
        self._toolbar.set_erase_enabled(False)
        self._sync_text_options_bar()

    def select_by_layer(self, name: str) -> None:
        """Selects every entity on layer `name` — the "select by layer" half
        of the selection options, exposed via a layer row's name button."""
        if self._doc is None:
            return
        handles = {entity.dxf.handle for entity in self._doc.modelspace if entity.dxf.layer == name}
        self._select_handles(handles)

    def _select_handles(self, handles: Iterable[str]) -> None:
        """Selects/highlights exactly the entities named by `handles`,
        looked up in the *current* scene — used after anything that changes
        what should be selected without going through a canvas click."""
        handle_set = set(handles)
        items = [item for item in self._view.scene().items() if item.data(_HANDLE_ROLE) in handle_set]
        self._view.set_selected_items(items)
        self._selected_handles = [item.data(_HANDLE_ROLE) for item in items]
        self._toolbar.set_erase_enabled(bool(items))
        self._sync_text_options_bar()

    def start_tool(self, tool: ToolSession) -> None:
        self.cancel_tool()
        self.clear_selection()
        self._active_tool = tool
        self._view.set_tool(tool)
        self._command_line.show_response(tool.prompt)
        self._command_line.focus_input()
        self._toolbar.set_active_tool(_TOOL_KEYS.get(type(tool)))

    def cancel_tool(self) -> None:
        if self._active_tool is not None:
            self._active_tool.cleanup(self._view.scene())
            self._active_tool = None
            self._view.set_tool(None)
            self._command_line.show_response("Cancelled.")
        self.clear_selection()
        self._toolbar.set_active_tool(None)

    def _start_draw_tool(self, factory: Callable[[], ToolSession]) -> None:
        """Toolbar entry point for Point/Line/Circle: auto-creates a blank
        document first, exactly like typing the bare command would."""
        self.ensure_document()
        self.start_tool(factory())

    def start_move_tool(self) -> None:
        """Toolbar/command-line entry point for Move — unlike the draw
        tools, this needs an existing selection and never auto-creates a
        document (there's nothing to move in a blank one)."""
        if not self._selected_handles:
            self._echo("Select objects to move first.")
            # The toolbar button already toggled itself checked on click
            # (Qt does that before this slot even runs) — since the tool
            # never actually started, put it back or it's left showing
            # "Move" active while clicks still do plain selection.
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(MoveToolSession(list(self._selected_handles)))

    def _on_add_layer(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self.ensure_document()
        self.execute_command(AddLayerCommand(name, rgb))

    def _on_prune_layers(self) -> None:
        if self._doc is None or self._imported_layer_names is None:
            return
        existing_names = {info.name for info in self._doc.iter_layers()}
        to_delete = layers_to_prune(self._imported_layer_names, existing_names)
        if not to_delete:
            self._echo("No layers to remove — everything already starts with 994, 211, or 219.")
            return
        preview = ", ".join(to_delete[:8]) + (f", +{len(to_delete) - 8} more" if len(to_delete) > 8 else "")
        confirmed = qw.QMessageBox.question(
            self,
            "Remove layers",
            f"Delete {len(to_delete)} imported layer(s) not starting with 994, 211, or 219, "
            f"along with everything drawn on them?\n\n{preview}\n\n"
            "Layers added since importing are not affected. This can be undone with Ctrl+Z.",
            qw.QMessageBox.StandardButton.Yes | qw.QMessageBox.StandardButton.No,
            qw.QMessageBox.StandardButton.No,
        )
        if confirmed != qw.QMessageBox.StandardButton.Yes:
            return
        self.execute_command(CompositeCommand([DeleteLayerCommand(name) for name in to_delete]))
        self._echo(f"Removed {len(to_delete)} layer(s).")

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
            self._command_line.focus_input()

    def _on_entity_selected(self, handles: List[str]) -> None:
        self._selected_handles = list(handles)
        self._toolbar.set_erase_enabled(bool(handles))
        self._sync_text_options_bar()

    def _on_items_drag_moved(self, handles: List[str], dx: float, dy: float) -> None:
        """Click-and-drag move finished on the canvas — same underlying
        MoveCommand as the Move tool, just triggered directly by dragging
        an entity instead of the base-point/second-point click sequence."""
        self._selected_handles = list(handles)
        self.execute_command(MoveCommand(handles, dx, dy))

    # -- Text options bar: shown above a single selected TEXT entity ------
    def _sync_text_options_bar(self) -> None:
        """Shows/hides/rebinds the floating text-options bar for whatever
        is selected right now — called after every selection change and
        after every render (edits, undo/redo, load/clear)."""
        if self._doc is None or len(self._selected_handles) != 1:
            self._text_options_bar.hide()
            return
        handle = self._selected_handles[0]
        entity = self._doc.get_entity(handle)
        if entity is None or entity.dxftype() != "TEXT":
            self._text_options_bar.hide()
            return
        self._text_options_bar.bind(
            handle, entity.dxf.text, entity.dxf.height, entity.dxf.rotation, self._doc.get_entity_color(handle)
        )
        self._reposition_text_options_bar()

    def _reposition_text_options_bar(self) -> None:
        bar = self._text_options_bar
        if not bar.isVisible() or bar.handle is None:
            return
        item = self._find_item(bar.handle)
        if item is None:
            bar.hide()
            return
        # Mapped via on-screen corners, not scene-space top/bottom: the
        # canvas is flipped (DXF is Y-up, Qt's scene is Y-down — see
        # CadGraphicsView.__init__), so "highest on screen" isn't simply
        # whichever corner has the smaller scene Y.
        rect = item.sceneBoundingRect()
        corners = [
            self._view.mapFromScene(rect.topLeft()),
            self._view.mapFromScene(rect.topRight()),
            self._view.mapFromScene(rect.bottomLeft()),
            self._view.mapFromScene(rect.bottomRight()),
        ]
        center_x = sum(p.x() for p in corners) / len(corners)
        top_y = min(p.y() for p in corners)
        global_point = self._view.viewport().mapToGlobal(qc.QPoint(round(center_x), round(top_y)))
        anchor = self.mapFromGlobal(global_point)
        bar.move(anchor.x() - bar.width() // 2, anchor.y() - bar.height() - SPACE_SM)
        bar.raise_()

    def _find_item(self, handle: str) -> Optional[qw.QGraphicsItem]:
        for item in self._view.scene().items():
            if item.data(_HANDLE_ROLE) == handle:
                return item
        return None

    # Selection carries over automatically: execute_command -> _render()
    # re-derives it from self._selected_handles, which already names this
    # entity (the bar is only bound/visible for a single selected TEXT).
    def _on_text_content_changed(self, handle: str, text: str) -> None:
        self.execute_command(SetTextContentCommand(handle, text))

    def _on_text_height_changed(self, handle: str, height: float) -> None:
        self.execute_command(SetTextHeightCommand(handle, height))

    def _on_text_rotation_changed(self, handle: str, rotation: float) -> None:
        self.execute_command(SetTextRotationCommand(handle, rotation))

    def _on_text_color_changed(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self.execute_command(SetEntityColorCommand(handle, rgb))

    def _finish_tool(self) -> None:
        tool = self._active_tool
        assert tool is not None
        doc = self.ensure_document()
        command = tool.build_command(doc.active_layer)
        # LINE and PIPE chain like AutoCAD's LINE: finishing a segment starts
        # a fresh session picking up from its endpoint instead of dropping
        # the tool, so drawing a connected run of segments doesn't require
        # reselecting the tool after every single click. Any ToolSession
        # that supports this just needs its own continuation() method.
        next_tool = tool.continuation() if hasattr(tool, "continuation") else None
        tool.cleanup(self._view.scene())
        self._active_tool = None
        self._view.set_tool(None)
        self._toolbar.set_active_tool(None)
        self.execute_command(command)
        if next_tool is not None:
            self.start_tool(next_tool)
            return
        # A command that exposes what it created (currently just
        # AddTextCommand) gets it auto-selected — e.g. so a just-placed
        # text is immediately ready for Delete/Move without a re-click.
        handle = getattr(command, "handle", None)
        if handle is not None:
            self._select_handles([handle])
        # Typing the last step's value (TEXT's content, an "@dx,dy" point,
        # ...) leaves focus in the command line — return it to the canvas
        # so Delete/Esc reach this widget's own shortcuts right away.
        self._view.setFocus()

    def _echo(self, message: str) -> None:
        self._command_line.show_response(message)

    def echo(self, message: str) -> None:
        """Shows `message` in this panel's own embedded command line — used
        by MainWindow's Edit menu (Undo/Redo live there now, not in this
        toolbar) so triggering this viewer's history from outside still
        reports through the same console every other edit action does."""
        self._echo(message)

    def can_undo(self) -> bool:
        return self._history is not None and self._history.can_undo()

    def can_redo(self) -> bool:
        return self._history is not None and self._history.can_redo()

    def _render(self, *, preserve_view: bool) -> None:
        assert self._doc is not None
        self._view.set_document(self._doc)
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

        handle_set = set(self._selected_handles)
        matched = [item for item in scene.items() if item.data(_HANDLE_ROLE) in handle_set]
        self._view.set_selected_items(matched)
        self._selected_handles = [item.data(_HANDLE_ROLE) for item in matched]
        self._toolbar.set_erase_enabled(bool(self._selected_handles))
        self.entity_count = self._doc.entity_count()
        self.layer_count = self._doc.layer_count()
        self._layer_panel.refresh(self._doc.iter_layers())
        self._layer_panel.set_prune_available(self._imported_layer_names is not None)
        self._sync_text_options_bar()
        self.documentChanged.emit()
