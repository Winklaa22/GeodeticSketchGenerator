from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.dxf_document import DXFDocument
from core.plot import PAPER_COLOR
from core.table_template import BORDER_WIDTH_MM, CELL_PADDING_MM, ResolvedCell
from core.detail_view import contains_point, handle_points
from ui.dxf.items import (
    CONTENT_PIVOT_PROPERTY,
    CONTENT_ROTATION_PROPERTY,
    DETAIL_CONTENT_ROLE,
    HANDLE_ROLE,
    PointItem,
    x_scale,
)
from ui.dxf.page_frame import PageFrame
from ui.dxf.stamp_cache import stamp_cache
from ui.theme import Color as UiColor
from ui.theme.qt_fonts import apply_font_family

if TYPE_CHECKING:
    from ui.dxf.tools import ToolSession


_CLICK_THRESHOLD_PX = 4
_SNAP_TOLERANCE_PX = 14
_DETAIL_HANDLE_PX = 7
# One per resize grip, in the order handle_points() returns them.
_DETAIL_HANDLE_CURSORS = (
    qc.Qt.CursorShape.SizeBDiagCursor,
    qc.Qt.CursorShape.SizeVerCursor,
    qc.Qt.CursorShape.SizeFDiagCursor,
    qc.Qt.CursorShape.SizeHorCursor,
    qc.Qt.CursorShape.SizeBDiagCursor,
    qc.Qt.CursorShape.SizeVerCursor,
    qc.Qt.CursorShape.SizeFDiagCursor,
    qc.Qt.CursorShape.SizeHorCursor,
)


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
    transform = item.sceneTransform()
    if isinstance(item, PointItem):
        pos = transform.map(item._pos)
        return math.hypot(point.x() - pos.x(), point.y() - pos.y())
    if isinstance(item, qw.QGraphicsLineItem):
        line = item.line()
        return _distance_to_segment(point, qc.QLineF(transform.map(line.p1()), transform.map(line.p2())))
    center = transform.mapRect(item.boundingRect()).center()
    return math.hypot(point.x() - center.x(), point.y() - center.y())


def _snap_candidates(item: qw.QGraphicsItem) -> Tuple[qc.QPointF, ...]:
    transform = item.sceneTransform()
    if isinstance(item, PointItem):
        return (transform.map(item._pos),)
    if isinstance(item, qw.QGraphicsLineItem):
        line = item.line()
        return (transform.map(line.p1()), transform.map(line.p2()))
    return ()


def _rotate_point(point: qc.QPointF, center: qc.QPointF, degrees: float) -> qc.QPointF:
    if not degrees:
        return point
    radians = math.radians(degrees)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    dx, dy = point.x() - center.x(), point.y() - center.y()
    return qc.QPointF(center.x() + dx * cos_a - dy * sin_a, center.y() + dx * sin_a + dy * cos_a)


class CadGraphicsView(qw.QGraphicsView):

    entitySelected = qc.pyqtSignal(list)
    toolPointPlaced = qc.pyqtSignal()
    itemsDragMoved = qc.pyqtSignal(list, float, float)
    viewportChanged = qc.pyqtSignal()
    pageFrameMoved = qc.pyqtSignal(float, float)
    # factor > 1 means "make the drawing bigger on the paper"; the anchor is the world
    # point under the cursor, which the new sheet scale has to keep in place.
    pageScaleZoomRequested = qc.pyqtSignal(float, float, float)
    detailZoomRequested = qc.pyqtSignal(str, float, float, float)
    detailPanRequested = qc.pyqtSignal(str, float, float)
    detailRotateRequested = qc.pyqtSignal(str, float)
    detailResizeRequested = qc.pyqtSignal(str, int, float, float)
    detailArrowAnchorPicked = qc.pyqtSignal(str, int)
    detailGestureFinished = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._base_scale = 1.0
        self._min_zoom = 0.02
        self._max_zoom = 200.0
        self._zoom_step = 0.2
        self._tool: Optional["ToolSession"] = None
        self._press_pos: Optional[qc.QPoint] = None
        self._selected_items: List[qw.QGraphicsItem] = []
        self._annotation_grips: List[qc.QPointF] = []
        self._detail_pan: Optional[Tuple[str, qc.QPointF]] = None
        self._tool_dragging = False
        self._detail_mode: Optional[str] = None
        self._detail_mode_handle: Optional[str] = None
        self._detail_rotate: Optional[Tuple[str, float]] = None
        self._detail_resize: Optional[Tuple[str, int]] = None
        self._pan_last_pos: Optional[qc.QPoint] = None
        self._rubber_band: Optional[qw.QRubberBand] = None
        self._snap_indicator: Optional[qc.QPointF] = None
        self._doc: Optional[DXFDocument] = None
        self._drag_candidate: Optional[qw.QGraphicsItem] = None
        self._dragging_items = False
        self._drag_items: List[qw.QGraphicsItem] = []
        self._drag_start_scene: Optional[qc.QPointF] = None
        self._page_frame: Optional[PageFrame] = None
        self._view_rotation = 0.0
        self._title_block_cells: List[ResolvedCell] = []
        self._title_block_scale = 1.0
        self._centre_hint: Optional[qc.QPointF] = None
        self._page_wheel_rest = 0

        self.setObjectName("dxfCanvas")
        self.setFocusPolicy(qc.Qt.FocusPolicy.StrongFocus)
        # Never AnchorUnderMouse: Qt resolves it through QCursor::pos(), which Wayland does
        # not expose - it reads back (0, 0) there, so every scale, rotate and resize would
        # re-anchor on the screen corner and throw the view sideways. Cursor-anchored wheel
        # zoom is done explicitly in zoom_by() instead.
        self.setTransformationAnchor(qw.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(qw.QGraphicsView.ViewportAnchor.AnchorViewCenter)
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

    def _fit_rect(self, rect: qc.QRectF, padding: float) -> None:
        span = max(rect.width(), rect.height()) or 1.0
        margin = span * padding
        padded = rect.adjusted(-margin, -margin, margin, margin)
        self.setSceneRect(self.scene().itemsBoundingRect().united(padded))
        self.fitInView(padded, qc.Qt.AspectRatioMode.KeepAspectRatio)
        self._base_scale = x_scale(self.transform())
        self._center_on(rect.center())
        self.viewportChanged.emit()

    def fit_to_scene(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        self._fit_rect(rect, 0.04)

    def fit_to_page(self) -> None:
        if self._page_frame is None:
            self.fit_to_scene()
            return
        self._refit_page(preserve_zoom=False)

    def _refit_page(
        self,
        preserve_zoom: bool,
        recenter_delta: Tuple[float, float] = (0.0, 0.0),
        center: Optional[qc.QPointF] = None,
    ) -> None:
        assert self._page_frame is not None
        zoom_factor = self._current_zoom() if preserve_zoom else 1.0
        # fitInView below always recenters on the sheet's own geometric center, which would
        # discard any off-center position the user reached by zooming with the mouse wheel.
        # Read where the view is actually centered now so it can be restored - shifted by
        # recenter_delta for a pan, unchanged for a resize - once the fit below is done.
        # Without this, every pan drag or window resize while zoomed in on a page snaps the
        # content back to dead-center, which reads as the view jumping sideways.
        prior_center = (center if center is not None else self._viewport_centre()) if preserve_zoom else None
        sheet = self._page_frame.sheet_rect()
        self.setSceneRect(sheet)
        self.fitInView(sheet, qc.Qt.AspectRatioMode.KeepAspectRatio)
        self._base_scale = x_scale(self.transform())
        if abs(zoom_factor - 1.0) > 1e-9:
            self.scale(zoom_factor, zoom_factor)
        if prior_center is not None:
            self._center_on(qc.QPointF(prior_center.x() + recenter_delta[0], prior_center.y() + recenter_delta[1]))
        else:
            self._center_on(sheet.center())
        self.viewportChanged.emit()

    def zoom_by(self, factor: float, anchor_pos: Optional[qc.QPointF] = None) -> bool:
        if factor <= 0:
            return False
        resulting_zoom = self._current_zoom() * factor
        if resulting_zoom < self._min_zoom or resulting_zoom > self._max_zoom:
            return False
        if anchor_pos is not None:
            # The wheel event's own position is the only trustworthy cursor position:
            # AnchorUnderMouse goes through QCursor::pos(), which is stale on X11 until the
            # widget has seen a real mouse press and simply (0, 0) on Wayland.
            # Worked out from the view the previous step meant to leave rather than read
            # back off the pixels: Qt stores the scroll position as whole pixels, so every
            # read-back inherits that step's rounding. With survey coordinates in the
            # millions the rounding is systematic, and a high-resolution wheel - several
            # events per notch on Linux, one on Windows - adds it up into a visible slide.
            before = self._scene_under(anchor_pos)
            self.scale(factor, factor)
            self._pin_under(before, anchor_pos)
        else:
            center = self._viewport_centre()
            self.scale(factor, factor)
            self._center_on(center)
        self.viewportChanged.emit()
        return True

    def zoom_window(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        rect = qc.QRectF(qc.QPointF(*p1), qc.QPointF(*p2)).normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        self.fitInView(rect, qc.Qt.AspectRatioMode.KeepAspectRatio)
        self._center_on(rect.center())
        return True

    def pan_by(self, dx: float, dy: float) -> None:
        if self._page_frame is not None:
            dx, dy = self._to_world_delta(dx, dy)
            self._page_frame = self._page_frame.moved_to(
                self._page_frame.center_x + dx, self._page_frame.center_y + dy
            )
            self._refit_page(preserve_zoom=True, recenter_delta=(dx, dy))
            self.pageFrameMoved.emit(self._page_frame.center_x, self._page_frame.center_y)
            return
        center = self._viewport_centre()
        self._center_on(qc.QPointF(center.x() + dx, center.y() + dy))
        self.viewportChanged.emit()

    def recenter_on(self, x: float, y: float) -> None:
        """Absolute pan to a scene point - the counterpart of pan_by's relative version.

        Widens sceneRect() first for the same reason restore_view() does: centerOn()
        clamps to the current sceneRect, which a fresh fit-to-scene sized to the content
        alone, not to wherever a remembered pan wants to look - without this, panning
        back towards the edge of (or past) that fitted rect silently falls short.
        """
        point = qc.QPointF(x, y)
        self._center_on(point)
        self.viewportChanged.emit()

    def default_duplicate_offset(self) -> Tuple[float, float]:
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        step = max(visible.width(), visible.height()) * 0.03
        if step <= 0:
            step = 1.0
        return step, step

    def save_view(self) -> Tuple[qg.QTransform, qc.QPointF, float, float]:
        """The zoom, plus the scene point the viewport is centred on.

        Scroll bar values cannot stand in for that point. Every render installs a fresh
        scene whose rect is its own items' bounding box, so as soon as the drawing's
        extents change - an edit, or switching to a tab that shows different content -
        the same scroll value points somewhere else entirely.
        """
        # A float centre; the integer QPoint one rounds the view by up to a pixel on
        # every save/restore round trip.
        return (
            self.transform(),
            self._viewport_centre(),
            self._view_rotation,
            self._base_scale,
        )

    def restore_view(self, saved: Tuple[qg.QTransform, qc.QPointF, float, float]) -> None:
        transform, center, rotation, base_scale = saved
        self.setTransform(transform)
        # The transform already carries the turn visually; the field has to agree with it,
        # or the next compass move would be measured against a stale angle.
        self._view_rotation = rotation
        self._base_scale = base_scale
        self._center_on(center)
        self.viewportChanged.emit()

    def _center_on(self, point: qc.QPointF) -> None:
        transform = self.transform()
        self.setTransform(qg.QTransform(
            transform.m11(), transform.m12(), transform.m21(), transform.m22(),
            -transform.m11() * point.x() - transform.m21() * point.y(),
            -transform.m12() * point.x() - transform.m22() * point.y(),
        ))
        self._widen_scene_rect_to(point)
        self.centerOn(point)
        self._centre_hint = qc.QPointF(point)

    def _viewport_centre(self) -> qc.QPointF:
        viewport = self.viewport()
        middle = qc.QPointF(viewport.width() / 2.0, viewport.height() / 2.0)
        hint = self._centre_hint
        if hint is not None:
            # centerOn() can only land within a pixel of what it was asked for; anything
            # further away means something else has moved the view since.
            shown = self.viewportTransform().map(hint)
            if abs(shown.x() - middle.x()) <= 1.5 and abs(shown.y() - middle.y()) <= 1.5:
                return qc.QPointF(hint)
        return self._scene_at(middle)

    def _scene_at(self, view_pos: qc.QPointF) -> qc.QPointF:
        inverse, _invertible = self.viewportTransform().inverted()
        return inverse.map(view_pos)

    def _device_to_scene_delta(self, dx: float, dy: float) -> qc.QPointF:
        t = self.transform()
        inverse, _invertible = qg.QTransform(t.m11(), t.m12(), t.m21(), t.m22(), 0.0, 0.0).inverted()
        return inverse.map(qc.QPointF(dx, dy))

    def _scene_under(self, view_pos: qc.QPointF) -> qc.QPointF:
        viewport = self.viewport()
        return self._viewport_centre() + self._device_to_scene_delta(
            view_pos.x() - viewport.width() / 2.0, view_pos.y() - viewport.height() / 2.0
        )

    def _pin_under(self, scene_point: qc.QPointF, view_pos: qc.QPointF) -> None:
        viewport = self.viewport()
        # centerOn() alone would clamp to sceneRect, which on a sheet is exactly the
        # paper - and that silently undoes the anchoring along the slack axis.
        target = scene_point + self._device_to_scene_delta(
            viewport.width() / 2.0 - view_pos.x(), viewport.height() / 2.0 - view_pos.y()
        )
        self._center_on(target)

    def _widen_scene_rect_to(self, center: qc.QPointF) -> None:
        """Keep centerOn() from clamping when the new scene is smaller than the old view."""
        wanted = self.mapToScene(self.viewport().rect().adjusted(-1, -1, 1, 1)).boundingRect()
        wanted.moveCenter(center)
        self.setSceneRect(self.sceneRect().united(wanted))

    def resizeEvent(self, event: qg.QResizeEvent) -> None:
        center = self._centre_hint
        super().resizeEvent(event)
        if self._page_frame is not None:
            # Re-fit whenever the viewport's actual size changes, not just on request: the
            # very first fit (right after the window/splitters are constructed) commonly
            # runs before layout has settled on the widget's final size, which used to
            # leave the page stuck small and off to one side until something else forced
            # a re-fit. Preserving zoom keeps this a no-op for the common "just resizing
            # the window" case rather than fighting whatever zoom the user had set.
            self._refit_page(preserve_zoom=True, center=center)
        else:
            self.viewportChanged.emit()

    def set_detail_mode(self, handle: Optional[str], mode: Optional[str]) -> None:
        self._detail_mode_handle = handle if mode else None
        self._detail_mode = mode or None
        self.viewport().update()

    def detail_mode(self) -> Optional[str]:
        return self._detail_mode

    def _mode_spec(self, mode: str):
        """The spec of the frame the given mode is armed for, if any."""
        if self._doc is None or self._detail_mode != mode or self._detail_mode_handle is None:
            return None
        return self._doc.detail_view_spec(self._detail_mode_handle)

    def _detail_target(self, world_point: qc.QPointF) -> Optional[str]:
        # Zooming and panning the magnified content only happens in the Edit mode of the
        # detail options bar; otherwise the wheel and the left button keep their usual
        # meaning over a selected frame.
        spec = self._mode_spec("edit")
        if spec is None:
            return None
        if not contains_point(spec, (world_point.x(), world_point.y())):
            return None
        return self._detail_mode_handle

    def wheelEvent(self, event: qg.QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120
        if notches == 0:
            return
        anchor_point = self._world_point(event.position())
        detail = self._detail_target(anchor_point)
        if detail is not None:
            self.reset_wheel_gesture()
            self.detailZoomRequested.emit(detail, notches, anchor_point.x(), anchor_point.y())
            event.accept()
            return
        factor = (1.0 + self._zoom_step) ** notches
        ctrl = bool(event.modifiers() & qc.Qt.KeyboardModifier.ControlModifier)
        # On a sheet, the plain wheel is a sheet edit rather than a view change: it
        # rescales the drawing on the paper (the page and its title block keep their
        # size), which is what gets exported. Ctrl+wheel stays a pure view zoom of the
        # whole preview. On the model tab there is no sheet to rescale, so the wheel
        # keeps its plain view-zoom meaning.
        if ctrl or self._page_frame is None:
            self.reset_wheel_gesture()
            self.zoom_by(factor, event.position())
            event.accept()
            return
        event.accept()
        # A high-resolution wheel (the usual case on Linux/Wayland) reports one notch as
        # several fractional events, where Windows sends a single 120. Every sheet-scale
        # step re-resolves and re-renders the whole sheet and rounds the scale to a whole
        # denominator, so collect the fractions and step once per full notch - the same
        # steps, renders and resulting scale on either platform.
        delta = event.angleDelta().y()
        if self._page_wheel_rest and (self._page_wheel_rest > 0) != (delta > 0):
            self._page_wheel_rest = 0
        self._page_wheel_rest += delta
        steps = int(self._page_wheel_rest / 120)
        if steps == 0:
            return
        self._page_wheel_rest -= steps * 120
        position = event.position()
        anchor = self._to_world(self._scene_under(position))
        self.pageScaleZoomRequested.emit((1.0 + self._zoom_step) ** steps, anchor.x(), anchor.y())
        if self._page_frame is not None:
            # The re-render refits the page, which on its own would drop a Ctrl+wheel zoom
            # back onto the sheet centre; keep the anchor under the cursor instead.
            self._pin_under(self._to_scene(anchor), position)
            self.viewportChanged.emit()

    def _world_point(self, view_pos: qc.QPointF) -> qc.QPointF:
        """Cursor position as a DXF/world point, undoing the scene's content rotation."""
        return self._to_world(self._scene_at(view_pos))

    def _to_world(self, scene_point: qc.QPointF) -> qc.QPointF:
        """A scene point as a DXF/world point, undoing the scene's content rotation."""
        rotation, pivot = self._content_rotation()
        if pivot is None:
            return scene_point
        return _rotate_point(scene_point, pivot, -rotation)

    def _to_scene(self, world_point: qc.QPointF) -> qc.QPointF:
        """A DXF/world point as a scene point - the inverse of :meth:`_to_world`.

        Anything painted in scene coordinates (the overlays in drawForeground) has to go
        through this, or on a rotated sheet it lands where the entity would be if the
        sheet were not turned, instead of on the entity.
        """
        rotation, pivot = self._content_rotation()
        if pivot is None:
            return world_point
        return _rotate_point(world_point, pivot, rotation)

    def _to_world_delta(self, dx: float, dy: float) -> Tuple[float, float]:
        """A scene-space drag as a DXF/world displacement.

        A displacement has no anchor, so only the content rotation applies - without this
        a drag on a rotated sheet would move the entity off in the direction the sheet is
        turned by.
        """
        rotation, pivot = self._content_rotation()
        if pivot is None:
            return dx, dy
        origin = qc.QPointF(0.0, 0.0)
        rotated = _rotate_point(qc.QPointF(dx, dy), origin, -rotation)
        return rotated.x(), rotated.y()

    def current_zoom_factor(self) -> float:
        return self._current_zoom()

    def apply_zoom_factor(self, factor: float) -> None:
        """Re-apply a zoom level relative to the page fit, without moving the centre.

        A relative multiply: calling this twice compounds. It exists for callers that
        know they are running exactly once, right after a guaranteed-fresh fit.
        """
        if factor <= 0 or abs(factor - 1.0) < 1e-9:
            return
        center = self._viewport_centre()
        self.scale(factor, factor)
        self._center_on(center)
        self.viewportChanged.emit()

    def set_zoom_factor(self, factor: float) -> None:
        """Set the zoom (relative to the fit) to an absolute target.

        Unlike apply_zoom_factor's relative multiply, this is idempotent - calling it
        again with the same target is a no-op. That matters here: restoring a remembered
        Model-tab view can run more than once for one tab switch (set_layout_mode's own
        render re-enters through documentChanged -> the app's "keep the sheet in sync"
        handler -> another reapply()), and a relative multiply would compound each time.
        """
        if factor <= 0:
            return
        current = self._current_zoom()
        if current <= 0 or abs(factor - current) < 1e-9:
            return
        center = self._viewport_centre()
        self.scale(factor / current, factor / current)
        self._center_on(center)
        self.viewportChanged.emit()

    def set_tool(self, tool: Optional["ToolSession"]) -> None:
        self._tool = tool
        self.setCursor(qc.Qt.CursorShape.CrossCursor if tool is not None else qc.Qt.CursorShape.ArrowCursor)
        if tool is None:
            self._set_snap_indicator(None)

    def set_document(self, doc: Optional[DXFDocument]) -> None:
        self._doc = doc

    def set_annotation_grips(self, grips: List[Tuple[float, float]]) -> None:
        self._annotation_grips = [qc.QPointF(*grip) for grip in grips]
        self.viewport().update()

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
        rotation, pivot = self._content_rotation()
        query_point = raw_scene_point if pivot is None else _rotate_point(raw_scene_point, pivot, -rotation)
        center = entity.dxf.center
        center_point = qc.QPointF(center.x, center.y)
        radius = entity.dxf.radius
        dx, dy = query_point.x() - center_point.x(), query_point.y() - center_point.y()
        dist_to_center = math.hypot(dx, dy)
        if radius <= 0 or dist_to_center <= 0:
            hover_point = center_point
        else:
            hover_point = qc.QPointF(
                center_point.x() + dx / dist_to_center * radius, center_point.y() + dy / dist_to_center * radius
            )
        if pivot is not None:
            hover_point = _rotate_point(hover_point, pivot, rotation)
            center_point = _rotate_point(center_point, pivot, rotation)
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
            if item.data(HANDLE_ROLE) is None or item.data(DETAIL_CONTENT_ROLE):
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

    def set_page_frame(self, frame: Optional[PageFrame]) -> None:
        if (frame is None) != (self._page_frame is None):
            self.reset_wheel_gesture()
        self._page_frame = frame
        self.viewport().update()

    def reset_wheel_gesture(self) -> None:
        self._page_wheel_rest = 0

    def set_title_block(self, cells: List[ResolvedCell], scale: float = 1.0) -> None:
        self._title_block_cells = cells
        self._title_block_scale = scale
        self.viewport().update()

    def set_content_rotation(
        self, rotation_degrees: float, pivot: Optional[Tuple[float, float]]
    ) -> None:
        origin = qc.QPointF(*pivot) if pivot is not None else qc.QPointF(0.0, 0.0)
        scene = self.scene()
        applied = scene.property(CONTENT_ROTATION_PROPERTY)
        scene.setProperty(CONTENT_ROTATION_PROPERTY, rotation_degrees)
        scene.setProperty(CONTENT_PIVOT_PROPERTY, origin)
        if not rotation_degrees and not applied:
            return
        index_method = scene.itemIndexMethod()
        scene.setItemIndexMethod(qw.QGraphicsScene.ItemIndexMethod.NoIndex)
        try:
            for item in scene.items():
                if item.data(HANDLE_ROLE) is None:
                    continue
                item.setTransformOriginPoint(origin)
                item.setRotation(rotation_degrees)
        finally:
            scene.setItemIndexMethod(index_method)

    def _content_rotation(self) -> Tuple[float, Optional[qc.QPointF]]:
        if self._page_frame is None or not self._page_frame.rotation:
            return 0.0, None
        return self._page_frame.rotation, qc.QPointF(self._page_frame.center_x, self._page_frame.center_y)

    def page_frame_rotation(self) -> float:
        return self._page_frame.rotation if self._page_frame is not None else 0.0

    def rotate_page_frame_live(self, rotation: float) -> None:
        if self._page_frame is None:
            return
        self._page_frame = self._page_frame.rotated_to(rotation)
        self.set_content_rotation(
            self._page_frame.rotation, (self._page_frame.center_x, self._page_frame.center_y)
        )
        self.viewport().update()

    def view_rotation(self) -> float:
        return self._view_rotation

    def set_view_rotation(self, degrees: float) -> None:
        delta = degrees - self._view_rotation
        if abs(delta) < 1e-9:
            return
        center = self._viewport_centre()
        self.rotate(delta)
        self._center_on(center)
        self._view_rotation = degrees
        self.viewportChanged.emit()

    def reset_view_rotation(self) -> None:
        if self._view_rotation:
            self.set_view_rotation(0.0)

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
        self._tool_dragging = False
        if self._tool is not None and event.button() == qc.Qt.MouseButton.LeftButton:
            world = self._world_point(event.position())
            if self._tool.grab((world.x(), world.y()), self._gizmo_tolerance()):
                # The release of this same gesture is what finishes the drag, through the
                # tool's usual on_click - nothing else should treat it as a plain click.
                self._tool_dragging = True
                return
        if self._tool is None and event.button() == qc.Qt.MouseButton.LeftButton:
            world = self._world_point(event.position())
            detail = self._detail_target(world)
            if detail is not None:
                self._detail_pan = (detail, world)
                self.setCursor(qc.Qt.CursorShape.ClosedHandCursor)
                return
            if self._pick_detail_arrow_anchor(world):
                # Picking an anchor starts the arrow tool, so this gesture's release must
                # not reach it as the arrow's target point.
                self._press_pos = None
                return
            if self._begin_detail_resize(world) or self._begin_detail_rotate(world):
                return
            self._drag_candidate = self._detail_move_item(world) or self._topmost_handled_item(self._press_pos)
        super().mousePressEvent(event)

    def _pick_detail_arrow_anchor(self, world: qc.QPointF) -> bool:
        """In Arrow mode the eight frame grips are where a leader can start."""
        spec = self._mode_spec("arrow")
        if spec is None:
            return False
        index = self._detail_handle_at(spec, world)
        if index is None:
            return False
        self.detailArrowAnchorPicked.emit(self._detail_mode_handle, index)
        return True

    def _begin_detail_resize(self, world: qc.QPointF) -> bool:
        spec = self._mode_spec("scale")
        if spec is None:
            return False
        index = self._detail_handle_at(spec, world)
        if index is None:
            return False
        self._detail_resize = (self._detail_mode_handle, index)
        return True

    def _begin_detail_rotate(self, world: qc.QPointF) -> bool:
        spec = self._mode_spec("rotate")
        if spec is None or not contains_point(spec, (world.x(), world.y())):
            return False
        grab = math.degrees(math.atan2(world.y() - spec.center[1], world.x() - spec.center[0]))
        self._detail_rotate = (self._detail_mode_handle, grab - spec.rotation)
        self.setCursor(qc.Qt.CursorShape.ClosedHandCursor)
        return True

    def _detail_move_item(self, world: qc.QPointF) -> Optional[qw.QGraphicsItem]:
        """In Move mode the whole frame is grabbable, not just its border."""
        spec = self._mode_spec("move")
        if spec is None or not contains_point(spec, (world.x(), world.y())):
            return None
        for item in self._selected_items:
            if item.data(HANDLE_ROLE) == self._detail_mode_handle:
                return item
        return None

    def _scene_scale(self) -> float:
        return x_scale(self.transform()) or 1.0

    def _detail_handle_at(self, spec, world: qc.QPointF) -> Optional[int]:
        tolerance = _DETAIL_HANDLE_PX / max(self._scene_scale(), 1e-9)
        best_index: Optional[int] = None
        best_distance = tolerance
        for index, grip in enumerate(handle_points(spec)):
            distance = math.hypot(grip[0] - world.x(), grip[1] - world.y())
            if distance <= best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        if self._pan_last_pos is not None:
            pos = event.position().toPoint()
            old_scene = self.mapToScene(self._pan_last_pos)
            new_scene = self.mapToScene(pos)
            self._pan_last_pos = pos
            self.pan_by(old_scene.x() - new_scene.x(), old_scene.y() - new_scene.y())
            return
        if self._detail_pan is not None:
            handle, last = self._detail_pan
            world = self._world_point(event.position())
            dx, dy = world.x() - last.x(), world.y() - last.y()
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                self._detail_pan = (handle, world)
                self.detailPanRequested.emit(handle, dx, dy)
            return
        if self._detail_rotate is not None:
            handle, grab_offset = self._detail_rotate
            world = self._world_point(event.position())
            spec = self._doc.detail_view_spec(handle) if self._doc is not None else None
            if spec is not None:
                pointer = math.degrees(math.atan2(world.y() - spec.center[1], world.x() - spec.center[0]))
                self.detailRotateRequested.emit(handle, pointer - grab_offset - spec.rotation)
            return
        if self._detail_resize is not None:
            handle, index = self._detail_resize
            world = self._world_point(event.position())
            self.detailResizeRequested.emit(handle, index, world.x(), world.y())
            return
        super().mouseMoveEvent(event)
        if self._tool is None and self._detail_mode in ("scale", "arrow"):
            self._update_detail_handle_cursor(event.position())
        if self._tool is not None:
            view_pos = event.position().toPoint()
            raw_point = self.mapToScene(view_pos)
            if self._tool_dragging:
                # Snapping mid-drag would make the scale factor jump between whatever
                # geometry happens to be near the cursor.
                point, snapped = raw_point, False
            else:
                point, snapped = self._snap_point(view_pos, raw_point)
                self._update_gizmo_cursor(view_pos)
            self._set_snap_indicator(point if snapped else None)
            world = self._to_world(point)
            self._tool.update_preview((world.x(), world.y()), self.scene())
        elif self._press_pos is not None:
            view_pos = event.position().toPoint()
            moved = (view_pos - self._press_pos).manhattanLength()
            if moved <= _CLICK_THRESHOLD_PX:
                return
            if self._drag_candidate is not None:
                self._ensure_dragging_items(view_pos)
            else:
                self._update_rubber_band(view_pos)

    def _paint_selection_highlight(self, painter: qg.QPainter, scale: float, color: qg.QColor) -> None:
        pen = qg.QPen(color, 3)
        pen.setCosmetic(True)
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        for item in self._selected_items:
            painter.save()
            painter.setPen(pen)
            painter.setTransform(item.sceneTransform(), True)
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
                painter.setPen(qc.Qt.PenStyle.NoPen)
                fill_color = qg.QColor(color)
                fill_color.setAlpha(90)
                painter.fillRect(item.boundingRect(), fill_color)
            painter.restore()

    def _gizmo_tolerance(self) -> float:
        return _DETAIL_HANDLE_PX / max(self._scene_scale(), 1e-9)

    def _update_gizmo_cursor(self, position: qc.QPoint) -> None:
        gizmo = self._tool.gizmo() if self._tool is not None else None
        if gizmo is None:
            return
        world = self._world_point(qc.QPointF(position))
        tolerance = self._gizmo_tolerance()
        near = any(
            math.hypot(p[0] - world.x(), p[1] - world.y()) <= tolerance for p in gizmo.points()
        )
        self.setCursor(
            qc.Qt.CursorShape.PointingHandCursor if near else qc.Qt.CursorShape.CrossCursor
        )

    def _update_detail_handle_cursor(self, position: qc.QPointF) -> None:
        arrow_mode = self._detail_mode == "arrow"
        spec = self._mode_spec("arrow" if arrow_mode else "scale")
        index = self._detail_handle_at(spec, self._world_point(position)) if spec is not None else None
        if index is None:
            self.setCursor(qc.Qt.CursorShape.ArrowCursor)
        elif arrow_mode:
            self.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(_DETAIL_HANDLE_CURSORS[index])

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
        if self._detail_rotate is not None or self._detail_resize is not None:
            self._detail_rotate = None
            self._detail_resize = None
            self._press_pos = None
            self.setCursor(qc.Qt.CursorShape.ArrowCursor)
            self.detailGestureFinished.emit()
            return
        if self._detail_pan is not None:
            self._detail_pan = None
            self._press_pos = None
            self.setCursor(qc.Qt.CursorShape.ArrowCursor)
            self.detailGestureFinished.emit()
            return
        super().mouseReleaseEvent(event)
        if event.button() != qc.Qt.MouseButton.LeftButton or self._press_pos is None:
            return
        press_pos = self._press_pos
        release_pos = event.position().toPoint()
        self._press_pos = None
        if self._tool is not None:
            raw_point = self.mapToScene(release_pos)
            scene_point = raw_point if self._tool_dragging else self._snap_point(release_pos, raw_point)[0]
            self._tool_dragging = False
            world_point = self._to_world(scene_point)
            self._tool.on_click((world_point.x(), world_point.y()))
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
            world_dx, world_dy = self._to_world_delta(dx, dy)
            self.itemsDragMoved.emit(handles, world_dx, world_dy)

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
        return [
            item
            for item in self.items(rect)
            if item.data(HANDLE_ROLE) is not None and not item.data(DETAIL_CONTENT_ROLE)
        ]

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

    def drawBackground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._page_frame is not None:
            painter.save()
            painter.fillRect(self._page_frame.sheet_rect(), qg.QColor(PAPER_COLOR))
            painter.restore()

    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:
        scale = x_scale(painter.transform()) or 1.0
        color = qg.QColor(UiColor.ACCENT)

        if self._page_frame is not None:
            painter.save()
            self._paint_page_frame(painter, scale, rect)
            painter.restore()

        if self._snap_indicator is not None:
            self._paint_snap_indicator(painter, self._snap_indicator, scale, color)

        # Only the highlight below needs a selection. The grips must still be drawn
        # without one: starting a tool clears the selection, and a transform gizmo has to
        # stay on screen for the whole gesture.
        self._paint_selection_highlight(painter, scale, color)
        # Every grip below is a world point and this painter draws in scene coordinates.
        squares = [self._to_scene(grip) for grip in self._annotation_grips]
        resize_spec = self._mode_spec("scale")
        if resize_spec is not None:
            squares.extend(self._to_scene(qc.QPointF(x, y)) for x, y in handle_points(resize_spec))
        # Round grips mark where an arrow can start, so they never look like something
        # that could be dragged to resize the frame.
        arrow_spec = self._mode_spec("arrow")
        dots = (
            [self._to_scene(qc.QPointF(x, y)) for x, y in handle_points(arrow_spec)]
            if arrow_spec is not None
            else []
        )
        gizmo = self._tool.gizmo() if self._tool is not None else None
        if gizmo is not None:
            squares.extend(self._to_scene(qc.QPointF(x, y)) for x, y in gizmo.handles)
            if gizmo.knob is not None:
                dots.append(self._to_scene(qc.QPointF(*gizmo.knob)))
        if squares or dots:
            grip_pen = qg.QPen(color, 1.5)
            grip_pen.setCosmetic(True)
            painter.setPen(grip_pen)
            painter.setBrush(qg.QBrush(qg.QColor(UiColor.SURFACE), qc.Qt.BrushStyle.SolidPattern))
            radius = 4 / scale
            for grip in squares:
                painter.drawRect(qc.QRectF(grip.x() - radius, grip.y() - radius, radius * 2, radius * 2))
            for dot in dots:
                painter.drawEllipse(dot, radius, radius)
        if gizmo is not None:
            self._paint_gizmo_center(painter, self._to_scene(qc.QPointF(*gizmo.center)), scale, color)

    @staticmethod
    def _paint_gizmo_center(painter, center: qc.QPointF, scale: float, color) -> None:
        """A small cross on the point a transform turns or scales about."""
        pen = qg.QPen(color, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        arm = 5 / scale
        painter.drawLine(qc.QPointF(center.x() - arm, center.y()), qc.QPointF(center.x() + arm, center.y()))
        painter.drawLine(qc.QPointF(center.x(), center.y() - arm), qc.QPointF(center.x(), center.y() + arm))

    @staticmethod
    def _ring_path(outer: qc.QRectF, inner: qc.QRectF) -> qg.QPainterPath:
        path = qg.QPainterPath()
        path.addRect(outer)
        path.addRect(inner)
        path.setFillRule(qc.Qt.FillRule.OddEvenFill)
        return path

    def _paint_page_frame(self, painter: qg.QPainter, scale: float, exposed: qc.QRectF) -> None:
        assert self._page_frame is not None
        sheet = self._page_frame.sheet_rect()
        map_rect = self._page_frame.map_rect()
        table_rect = self._page_frame.table_rect()

        # The chrome shares the view's live transform with the drawing, so the exposed
        # scene rect really is what the viewport shows: mask everything outside the sheet
        # with it, and the canvas stays covered at any zoom. United with the sheet so the
        # ring is never empty when the page is larger than the visible area.
        outer = exposed.united(sheet)
        painter.fillPath(self._ring_path(outer, sheet), qg.QColor(UiColor.SURFACE_SUNKEN))
        painter.fillPath(self._ring_path(sheet, map_rect), qg.QColor(PAPER_COLOR))

        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        sheet_pen = qg.QPen(qg.QColor(0, 0, 0, 130), 1.4)
        sheet_pen.setCosmetic(True)
        painter.setPen(sheet_pen)
        painter.drawRect(sheet)

        border_width = max(BORDER_WIDTH_MM * self._title_block_scale, 0.02)
        solid_pen = qg.QPen(qg.QColor(0, 0, 0), border_width)
        solid_pen.setCosmetic(False)
        painter.setPen(solid_pen)
        if map_rect.height() > 0.0:
            painter.drawRect(map_rect)
        if table_rect.height() > 0.0:
            painter.drawRect(table_rect)
            self._paint_title_block_table(painter, table_rect, border_width)

        if self._page_frame.label:
            self._paint_frame_label(painter, sheet, scale, self._page_frame.label)

    def _paint_title_block_table(
        self, painter: qg.QPainter, table_rect: qc.QRectF, border_width: float
    ) -> None:
        if not self._title_block_cells:
            return
        # Cells are computed in a LOCAL, Y-down frame (row 0 = header, at the top of the
        # table). Placing them with translate(left, bottom) + scale(1, -1) both (a) maps
        # that local frame onto the scene's Y-up table_rect with the header ending up next
        # to the map (as intended), and (b) cancels the view's own Y-flip for anything
        # drawn here, so text/logos render upright with no separate correction needed.
        painter.save()
        painter.translate(table_rect.left(), table_rect.bottom())
        painter.scale(1.0, -1.0)
        thin_pen = qg.QPen(qg.QColor(0, 0, 0), max(border_width * 0.6, 0.015))
        thin_pen.setCosmetic(False)
        padding = CELL_PADDING_MM * self._title_block_scale
        for cell in self._title_block_cells:
            cell_rect = qc.QRectF(cell.rect.x, cell.rect.y, cell.rect.w, cell.rect.h)
            painter.setPen(thin_pen)
            painter.setBrush(qc.Qt.BrushStyle.NoBrush)
            painter.drawRect(cell_rect)
            padded = cell_rect.adjusted(padding, padding, -padding, -padding)
            if cell.kind == "image" and cell.image_path:
                self._paint_cell_image(painter, padded, cell.image_path)
            elif cell.text:
                self._paint_cell_text(painter, padded, cell)
        painter.restore()

    @staticmethod
    def _paint_cell_image(painter: qg.QPainter, rect: qc.QRectF, path: str) -> None:
        pixmap = stamp_cache.get(path)
        if pixmap is None or pixmap.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        src_w, src_h = pixmap.width(), pixmap.height()
        if src_w <= 0 or src_h <= 0:
            return
        scale = min(rect.width() / src_w, rect.height() / src_h)
        target = qc.QRectF(0.0, 0.0, src_w * scale, src_h * scale)
        target.moveCenter(rect.center())
        painter.setRenderHint(qg.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(target, pixmap, qc.QRectF(0.0, 0.0, float(src_w), float(src_h)))

    @staticmethod
    def _cell_flags(cell: ResolvedCell) -> int:
        align = {
            "left": qc.Qt.AlignmentFlag.AlignLeft,
            "center": qc.Qt.AlignmentFlag.AlignHCenter,
            "right": qc.Qt.AlignmentFlag.AlignRight,
        }.get(cell.align, qc.Qt.AlignmentFlag.AlignLeft)
        valign = {
            "top": qc.Qt.AlignmentFlag.AlignTop,
            "middle": qc.Qt.AlignmentFlag.AlignVCenter,
            "bottom": qc.Qt.AlignmentFlag.AlignBottom,
        }.get(cell.valign, qc.Qt.AlignmentFlag.AlignTop)
        return int(align) | int(valign) | int(qc.Qt.TextFlag.TextWordWrap)

    _TEXT_REFERENCE_PX = 200.0

    @classmethod
    def _draw_scaled_text(
        cls,
        painter: qg.QPainter,
        rect: qc.QRectF,
        flags: int,
        text: str,
        font_size: float,
        bold: bool = False,
        italic: bool = False,
        font_id: str = "",
    ) -> None:
        if font_size <= 0.0 or not text:
            return
        # cell.font_size is a small scene-unit value (often well under 2). Asking Qt's font
        # rasterizer for that size directly is unreliable: glyphs are hinted onto an integer
        # pixel grid, so at a couple of "points" Qt quantizes/clamps outright (measured:
        # 1.5, 1.6, 1.7 and 1.8pt all rasterize to the exact same height). As cell.font_size
        # drifts continuously with the sheet's scale, that quantization makes the on-screen
        # text visibly snap between sizes while zooming. Fix: render at a large, stable
        # reference pixel size (negligible relative rounding error) and reach the actual
        # target size via a continuous painter scale instead, which the view's own zoom then
        # magnifies smoothly with no further quantization.
        local_scale = font_size / cls._TEXT_REFERENCE_PX
        painter.save()
        painter.translate(rect.left(), rect.top())
        painter.scale(local_scale, local_scale)
        font = apply_font_family(qg.QFont(), font_id) if font_id else qg.QFont()
        font.setPixelSize(round(cls._TEXT_REFERENCE_PX))
        font.setBold(bold)
        font.setItalic(italic)
        painter.setFont(font)
        painter.setPen(qg.QColor(0, 0, 0))
        local_rect = qc.QRectF(0.0, 0.0, rect.width() / local_scale, rect.height() / local_scale)
        painter.drawText(local_rect, flags, text)
        painter.restore()

    @classmethod
    def _paint_cell_text(cls, painter: qg.QPainter, rect: qc.QRectF, cell: ResolvedCell) -> None:
        cls._draw_scaled_text(
            painter, rect, cls._cell_flags(cell), cell.text, cell.font_size, cell.bold, cell.italic,
            cell.font_id,
        )

    @staticmethod
    def _paint_frame_label(
        painter: qg.QPainter, sheet: qc.QRectF, scale: float, label: str
    ) -> None:
        painter.save()
        painter.translate(sheet.left(), sheet.top())
        painter.scale(1.0 / scale, -1.0 / scale)
        font = painter.font()
        font.setPointSizeF(9.0)
        painter.setFont(font)
        painter.setPen(qg.QPen(qg.QColor(UiColor.TEXT_MUTED)))
        painter.drawText(qc.QPointF(0.0, 14.0), label)
        painter.restore()

    @staticmethod
    def _paint_snap_indicator(painter: qg.QPainter, point: qc.QPointF, scale: float, color: qg.QColor) -> None:
        # A translucent tinted fill, not just an outline: at this size a hairline square
        # all but disappears against a busy drawing or the white sheet background, and a
        # solid fill would hide the very point/line it's marking as the snap target.
        pen = qg.QPen(color, 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        fill_color = qg.QColor(color)
        fill_color.setAlpha(90)
        painter.setBrush(qg.QBrush(fill_color, qc.Qt.BrushStyle.SolidPattern))
        half = 4.5 / scale
        painter.drawRect(qc.QRectF(point.x() - half, point.y() - half, half * 2, half * 2))
