from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.dxf_document import DXFDocument
from ui.dxf.items import HANDLE_ROLE, PointItem, x_scale
from ui.theme import Color as UiColor

if TYPE_CHECKING:
    from ui.dxf.tools import ToolSession


_CLICK_THRESHOLD_PX = 4
_SNAP_TOLERANCE_PX = 14


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
    if isinstance(item, PointItem):
        return math.hypot(point.x() - item._pos.x(), point.y() - item._pos.y())
    if isinstance(item, qw.QGraphicsLineItem):
        return _distance_to_segment(point, item.line())
    center = item.sceneTransform().mapRect(item.boundingRect()).center()
    return math.hypot(point.x() - center.x(), point.y() - center.y())


def _snap_candidates(item: qw.QGraphicsItem) -> Tuple[qc.QPointF, ...]:
    if isinstance(item, PointItem):
        return (item._pos,)
    if isinstance(item, qw.QGraphicsLineItem):
        line = item.line()
        return (line.p1(), line.p2())
    return ()


class CadGraphicsView(qw.QGraphicsView):

    entitySelected = qc.pyqtSignal(list)
    toolPointPlaced = qc.pyqtSignal()
    itemsDragMoved = qc.pyqtSignal(list, float, float)
    viewportChanged = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._base_scale = 1.0
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
        self._drag_candidate: Optional[qw.QGraphicsItem] = None
        self._dragging_items = False
        self._drag_items: List[qw.QGraphicsItem] = []
        self._drag_start_scene: Optional[qc.QPointF] = None

        self.setObjectName("dxfCanvas")
        self.setFocusPolicy(qc.Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(qw.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
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
        self.scale(1, -1)

    def _current_zoom(self) -> float:
        return x_scale(self.transform()) / (self._base_scale or 1.0)

    def fit_to_scene(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        margin = (max(rect.width(), rect.height()) * 0.04) or 1.0
        rect = rect.adjusted(-margin, -margin, margin, margin)
        self.setSceneRect(rect)
        self.fitInView(rect, qc.Qt.AspectRatioMode.KeepAspectRatio)
        self._base_scale = x_scale(self.transform())
        self.viewportChanged.emit()

    def zoom_by(self, factor: float) -> bool:
        if factor <= 0:
            return False
        resulting_zoom = self._current_zoom() * factor
        if resulting_zoom < self._min_zoom or resulting_zoom > self._max_zoom:
            return False
        self.scale(factor, factor)
        self.viewportChanged.emit()
        return True

    def zoom_window(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        rect = qc.QRectF(qc.QPointF(*p1), qc.QPointF(*p2)).normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        self.fitInView(rect, qc.Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def pan_by(self, dx: float, dy: float) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center.x() + dx, center.y() + dy)
        self.viewportChanged.emit()

    def default_duplicate_offset(self) -> Tuple[float, float]:
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        step = max(visible.width(), visible.height()) * 0.03
        if step <= 0:
            step = 1.0
        return step, step

    def save_view(self) -> Tuple[qg.QTransform, int, int]:
        return self.transform(), self.horizontalScrollBar().value(), self.verticalScrollBar().value()

    def restore_view(self, saved: Tuple[qg.QTransform, int, int]) -> None:
        transform, h_value, v_value = saved
        self.setTransform(transform)
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)
        self.viewportChanged.emit()

    def resizeEvent(self, event: qg.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.viewportChanged.emit()

    def wheelEvent(self, event: qg.QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120
        if notches == 0:
            return
        factor = (1.0 + self._zoom_step) ** notches
        self.zoom_by(factor)

    def set_tool(self, tool: Optional["ToolSession"]) -> None:
        self._tool = tool
        self.setCursor(qc.Qt.CursorShape.CrossCursor if tool is not None else qc.Qt.CursorShape.ArrowCursor)
        if tool is None:
            self._set_snap_indicator(None)

    def set_document(self, doc: Optional[DXFDocument]) -> None:
        self._doc = doc

    def _snap_candidates_for(
        self, item: qw.QGraphicsItem, raw_scene_point: qc.QPointF
    ) -> Tuple[Tuple[qc.QPointF, qc.QPointF], ...]:
        plain = _snap_candidates(item)
        if plain:
            return tuple((point, point) for point in plain)
        if self._doc is None:
            return ()
        handle = item.data(HANDLE_ROLE)
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
        rect = qc.QRect(
            view_pos.x() - _SNAP_TOLERANCE_PX,
            view_pos.y() - _SNAP_TOLERANCE_PX,
            _SNAP_TOLERANCE_PX * 2,
            _SNAP_TOLERANCE_PX * 2,
        )
        best_point: Optional[qc.QPointF] = None
        best_distance = float(_SNAP_TOLERANCE_PX)
        for item in self.items(rect):
            if item.data(HANDLE_ROLE) is None:
                continue
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
        if self._snap_indicator == point:
            return
        self._snap_indicator = point
        self.viewport().update()

    def set_selected_item(self, item: Optional[qw.QGraphicsItem]) -> None:
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
        handles = [item.data(HANDLE_ROLE) for item in self._selected_items]
        self.entitySelected.emit(handles)

    def mousePressEvent(self, event: qg.QMouseEvent) -> None:
        if event.button() == qc.Qt.MouseButton.MiddleButton:
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(qc.Qt.CursorShape.ClosedHandCursor)
            return
        self._press_pos = event.position().toPoint()
        self._drag_candidate = None
        if self._tool is None and event.button() == qc.Qt.MouseButton.LeftButton:
            self._drag_candidate = self._topmost_handled_item(self._press_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        if self._pan_last_pos is not None:
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

    def mouseReleaseEvent(self, event: qg.QMouseEvent) -> None:
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
            raw_point = self.mapToScene(release_pos)
            scene_point, _ = self._snap_point(release_pos, raw_point)
            self._tool.on_click((scene_point.x(), scene_point.y()))
            self.toolPointPlaced.emit()
            return
        if self._dragging_items:
            self._finish_drag_items(release_pos)
            return
        additive_mask = qc.Qt.KeyboardModifier.ShiftModifier | qc.Qt.KeyboardModifier.ControlModifier
        additive = bool(event.modifiers() & additive_mask)
        moved = (release_pos - press_pos).manhattanLength()
        if moved > _CLICK_THRESHOLD_PX:
            self._finish_rubber_band(press_pos, release_pos, additive=additive)
            return
        item = self._topmost_handled_item(release_pos)
        if additive:
            self._toggle_selected_item(item)
        else:
            self.set_selected_items([item] if item is not None else [])
        self._emit_selection()

    def _finish_drag_items(self, release_pos: qc.QPoint) -> None:
        assert self._drag_start_scene is not None
        current_scene = self.mapToScene(release_pos)
        dx = current_scene.x() - self._drag_start_scene.x()
        dy = current_scene.y() - self._drag_start_scene.y()
        handles = [item.data(HANDLE_ROLE) for item in self._drag_items]
        for item in self._drag_items:
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
        return [item for item in self.items(rect) if item.data(HANDLE_ROLE) is not None]

    def _topmost_handled_item(self, view_pos: qc.QPoint) -> Optional[qw.QGraphicsItem]:
        tolerance = 4
        rect = qc.QRect(view_pos.x() - tolerance, view_pos.y() - tolerance, tolerance * 2, tolerance * 2)
        click_scene = self.mapToScene(view_pos)
        best_item: Optional[qw.QGraphicsItem] = None
        best_distance = math.inf
        for item in self.items(rect):
            if item.data(HANDLE_ROLE) is None:
                continue
            distance = _distance_to_item(click_scene, item)
            if distance < best_distance:
                best_distance = distance
                best_item = item
        return best_item

    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:
        scale = x_scale(painter.transform()) or 1.0
        color = qg.QColor(UiColor.ACCENT)

        if self._snap_indicator is not None:
            self._paint_snap_indicator(painter, self._snap_indicator, scale, color)

        if not self._selected_items:
            return
        pen = qg.QPen(color, 3)
        pen.setCosmetic(True)
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        for item in self._selected_items:
            if isinstance(item, PointItem):
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
        pen = qg.QPen(color, 1.6)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        half = 4.5 / scale
        painter.drawRect(qc.QRectF(point.x() - half, point.y() - half, half * 2, half * 2))

