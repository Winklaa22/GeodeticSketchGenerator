from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.edit import MoveCommand, RotateCommand, ScaleCommand
from core.commands.text import SetTextRotationCommand
from core.dxf_document import DXFDocument
from core.transform_gizmo import (
    Box,
    bbox_corners,
    center_of,
    knob_point,
    rotation_delta,
    scale_factor,
)
from ui.dxf.items import HANDLE_ROLE
from ui.dxf.tools.base import (
    Gizmo,
    ToolSession,
    add_preview_item,
    angle_degrees,
    parse_coordinate,
    point_distance,
    preview_pen,
    to_scene_point,
)
from ui.i18n import tr


# Previews transform the real scene items. On a sheet those items already carry the
# layout's rotation via setRotation()/setTransformOriginPoint(), so a preview must not
# touch either - it goes through setTransform() instead. Qt applies that transform
# *after* the item's own rotation, i.e. in scene coordinates, so every origin below is
# mapped world -> scene first; skipping that is what made previewed objects jump away
# on a rotated sheet and snap back when the gesture finished.
def _preview_targets(scene: qw.QGraphicsScene, handles: List[str]) -> List[qw.QGraphicsItem]:
    handle_set = set(handles)
    return [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]


def _rotation_about(origin: qc.QPointF, degrees: float) -> qg.QTransform:
    return (
        qg.QTransform()
        .translate(origin.x(), origin.y())
        .rotate(degrees)
        .translate(-origin.x(), -origin.y())
    )


def _scaling_about(origin: qc.QPointF, factor: float) -> qg.QTransform:
    return (
        qg.QTransform()
        .translate(origin.x(), origin.y())
        .scale(factor, factor)
        .translate(-origin.x(), -origin.y())
    )


def _knob_offset(box: Box) -> float:
    """How far above the box the rotation grip floats - a share of its own size."""
    (min_x, min_y), (max_x, max_y) = box
    return max(max_x - min_x, max_y - min_y) * 0.25 or 1.0


def _item_center(item: qw.QGraphicsItem) -> qc.QPointF:
    """An item's own centre in scene coordinates, ignoring any preview transform."""
    center = item.boundingRect().center()
    spin = qg.QTransform()
    spin.translate(item.transformOriginPoint().x(), item.transformOriginPoint().y())
    spin.rotate(item.rotation())
    spin.translate(-item.transformOriginPoint().x(), -item.transformOriginPoint().y())
    return spin.map(center)


def _clear_preview_transforms(items: Optional[List[qw.QGraphicsItem]]) -> None:
    for item in items or ():
        item.setTransform(qg.QTransform())


class MoveToolSession(ToolSession):

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_base_point")
        self._base: Optional[Tuple[float, float]] = None
        self._dest: Optional[Tuple[float, float]] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_second_point")
        else:
            self._dest = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=self._base)
        if coord is None:
            return tr("common.point_xy_or_rel_format", value=text)
        if self._base is None:
            self._base = coord
            self.prompt = tr("tool.specify_second_point")
        else:
            self._dest = coord
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._dest is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

    def is_done(self) -> bool:
        return self._base is not None and self._dest is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._base is not None and self._dest is not None
        dx = self._dest[0] - self._base[0]
        dy = self._dest[1] - self._base[1]
        return MoveCommand(self._handles, dx, dy)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None


class RotateToolSession(ToolSession):
    """Drag the grip beside the selection; it turns about the selection's own centre."""

    def __init__(self, handles: List[str], box: Optional[Box] = None) -> None:
        super().__init__()
        self._handles = handles
        self._box = box
        self._center: Optional[Tuple[float, float]] = center_of(*box) if box is not None else None
        self._knob: Optional[Tuple[float, float]] = None
        self._grab: Optional[Tuple[float, float]] = None
        # Without a box there is nothing to put a gizmo on, so fall back to picking a
        # base point and an angle by hand.
        self._base: Optional[Tuple[float, float]] = self._center
        self.prompt = tr("tool.rotate_gizmo_hint" if box is not None else "tool.specify_base_point")
        self._angle: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def gizmo(self) -> Optional[Gizmo]:
        if self._box is None or self._center is None or self._angle is not None:
            return None
        self._knob = knob_point(*self._box, offset=_knob_offset(self._box))
        return Gizmo(center=self._center, knob=self._knob)

    def grab(self, point: Tuple[float, float], tolerance: float) -> bool:
        if self._knob is None:
            return False
        if point_distance(self._knob, point) > tolerance:
            return False
        self._grab = self._knob
        return True

    def _dragged_angle(self, point: Tuple[float, float]) -> Optional[float]:
        if self._center is None or self._grab is None:
            return None
        return rotation_delta(self._center, self._grab, point)

    def on_click(self, point: Tuple[float, float]) -> None:
        angle = self._dragged_angle(point)
        if angle is not None:
            self._angle = angle
            return
        if self._box is not None:
            return  # a click that grabbed nothing: the gizmo stays waiting
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_rotation_angle")
        else:
            self._angle = angle_degrees(self._base, point)

    def on_text(self, text: str) -> Optional[str]:
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_rotation_angle")
            return None
        try:
            angle = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.angle_or_point_numeric", value=text)
            angle = angle_degrees(self._base, coord)
        self._angle = angle
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._angle is not None:
            return
        angle = self._dragged_angle(point)
        if angle is None:
            if self._box is not None:
                return  # nothing grabbed yet - the selection must stay put
            angle = angle_degrees(self._base, point)
            self._draw_rubber_line(self._base, point, scene)
        else:
            self._draw_rubber_line(self._center, point, scene)

        if self._preview_targets is None:
            self._preview_targets = _preview_targets(scene, self._handles)
        spin = _rotation_about(to_scene_point(scene, self._base), angle)
        for item in self._preview_targets:
            item.setTransform(spin)

    def _draw_rubber_line(self, start, point, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(start[0], start[1], point[0], point[1])

    def is_done(self) -> bool:
        return self._base is not None and self._angle is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._base is not None and self._angle is not None
        return RotateCommand(self._handles, self._angle, self._base)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        _clear_preview_transforms(self._preview_targets)
        self._preview_targets = None


class ScaleToolSession(ToolSession):
    """Drag a corner grip; the selection grows about its own centre, which stays put.

    The factor is a ratio of two distances from that centre, so the same drag means the
    same thing however far the view is zoomed out - on a fitted sheet the drawing can be
    a few dozen pixels wide, where a distance measured in drawing units is meaningless.
    """

    def __init__(self, handles: List[str], box: Optional[Box] = None) -> None:
        super().__init__()
        self._handles = handles
        self._box = box
        self._center: Optional[Tuple[float, float]] = center_of(*box) if box is not None else None
        self._corners: Tuple[Tuple[float, float], ...] = bbox_corners(*box) if box is not None else ()
        self._grab: Optional[Tuple[float, float]] = None
        self._reference_mode = box is None
        self._base: Optional[Tuple[float, float]] = self._center
        self.prompt = tr("tool.scale_gizmo_hint" if box is not None else "tool.specify_base_point")
        self._reference: Optional[float] = None
        self._factor: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def gizmo(self) -> Optional[Gizmo]:
        if self._box is None or self._reference_mode or self._center is None or self._factor is not None:
            return None
        return Gizmo(center=self._center, handles=self._corners)

    def grab(self, point: Tuple[float, float], tolerance: float) -> bool:
        if self._reference_mode or not self._corners:
            return False
        nearest = min(self._corners, key=lambda corner: point_distance(corner, point))
        if point_distance(nearest, point) > tolerance:
            return False
        self._grab = nearest
        return True

    def _dragged_factor(self, point: Tuple[float, float]) -> Optional[float]:
        if self._center is None or self._grab is None:
            return None
        return scale_factor(self._center, self._grab, point)

    def _enter_reference_mode(self) -> None:
        self._reference_mode = True
        self._grab = None
        self._base = None
        self._reference = None
        self.prompt = tr("tool.specify_base_point")

    def _set_reference(self, length: float) -> None:
        self._reference = length
        self.prompt = tr("tool.specify_new_length")

    def _reference_factor(self, point: Tuple[float, float]) -> Optional[float]:
        if self._base is None or self._reference is None or self._reference <= 0:
            return None
        factor = point_distance(self._base, point) / self._reference
        return factor if factor > 0 else None

    def on_click(self, point: Tuple[float, float]) -> None:
        if not self._reference_mode:
            factor = self._dragged_factor(point)
            if factor is not None:
                self._factor = factor
            return
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_reference_length")
            return
        if self._reference is None:
            length = point_distance(self._base, point)
            if length > 0:
                self._set_reference(length)
            return
        factor = self._reference_factor(point)
        if factor is not None:
            self._factor = factor

    def on_text(self, text: str) -> Optional[str]:
        if text.strip().upper() in {"R", "REF", "REFERENCE"} and not self._reference_mode:
            self._enter_reference_mode()
            return None
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_reference_length")
            return None
        # A typed number is still the factor itself - the quickest way to an exact scale.
        try:
            factor = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.scale_or_point_numeric", value=text)
            if self._reference_mode and self._reference is None:
                length = point_distance(self._base, coord)
                if length <= 0:
                    return tr("common.scale_positive")
                self._set_reference(length)
                return None
            factor = (self._reference_factor(coord) if self._reference_mode
                      else self._dragged_factor(coord)) or 0.0
        if factor <= 0:
            return tr("common.scale_positive")
        self._factor = factor
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._factor is not None:
            return
        factor = self._reference_factor(point) if self._reference_mode else self._dragged_factor(point)
        if factor is None:
            return  # nothing grabbed, or no reference length yet: leave the drawing alone
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            self._preview_targets = _preview_targets(scene, self._handles)
        resize = _scaling_about(to_scene_point(scene, self._base), factor)
        for item in self._preview_targets:
            item.setTransform(resize)

    def is_done(self) -> bool:
        return self._base is not None and self._factor is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._base is not None and self._factor is not None
        return ScaleCommand(self._handles, self._factor, self._base)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        _clear_preview_transforms(self._preview_targets)
        self._preview_targets = None


class RotateEachToolSession(ToolSession):

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_reference_point")
        self._base: Optional[Tuple[float, float]] = None
        self._angle: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_rotation_angle")
        else:
            self._angle = angle_degrees(self._base, point)

    def on_text(self, text: str) -> Optional[str]:
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_rotation_angle")
            return None
        try:
            angle = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.angle_or_point_numeric", value=text)
            angle = angle_degrees(self._base, coord)
        self._angle = angle
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._angle is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            self._preview_targets = _preview_targets(scene, self._handles)
        angle = angle_degrees(self._base, point)
        for item in self._preview_targets:
            item.setTransform(_rotation_about(_item_center(item), angle))

    def is_done(self) -> bool:
        return self._base is not None and self._angle is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._angle is not None
        return CompositeCommand(
            [RotateCommand([handle], self._angle, doc.entity_center(handle)) for handle in self._handles]
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        _clear_preview_transforms(self._preview_targets)
        self._preview_targets = None


class ScaleEachToolSession(ToolSession):

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_reference_point")
        self._base: Optional[Tuple[float, float]] = None
        self._reference: Optional[float] = None
        self._factor: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def _set_reference(self, length: float) -> None:
        self._reference = length
        self.prompt = tr("tool.specify_new_length")

    def _preview_factor(self, point: Tuple[float, float]) -> Optional[float]:
        if self._base is None or self._reference is None or self._reference <= 0:
            return None
        factor = point_distance(self._base, point) / self._reference
        return factor if factor > 0 else None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_reference_length")
            return
        if self._reference is None:
            length = point_distance(self._base, point)
            if length > 0:
                self._set_reference(length)
            return
        factor = self._preview_factor(point)
        if factor is not None:
            self._factor = factor

    def on_text(self, text: str) -> Optional[str]:
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_reference_length")
            return None
        try:
            factor = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.scale_or_point_numeric", value=text)
            if self._reference is None:
                length = point_distance(self._base, coord)
                if length <= 0:
                    return tr("common.scale_positive")
                self._set_reference(length)
                return None
            factor = self._preview_factor(coord) or 0.0
        if factor <= 0:
            return tr("common.scale_positive")
        self._factor = factor
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._base is None or self._factor is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsLineItem()
            self._preview_item.setPen(preview_pen())
            add_preview_item(scene, self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            self._preview_targets = _preview_targets(scene, self._handles)
        factor = self._preview_factor(point)
        if factor is None:
            return
        for item in self._preview_targets:
            item.setTransform(_scaling_about(_item_center(item), factor))

    def is_done(self) -> bool:
        return self._base is not None and self._factor is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._factor is not None
        return CompositeCommand(
            [ScaleCommand([handle], self._factor, doc.entity_center(handle)) for handle in self._handles]
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        _clear_preview_transforms(self._preview_targets)
        self._preview_targets = None


def upright_angle(angle_deg: float) -> float:
    """A direction angle turned around when it would leave text reading upside down."""
    angle_deg %= 360
    if angle_deg < 0:
        angle_deg += 360
    if 90 < angle_deg < 270:
        angle_deg -= 180
    return angle_deg


class TextOnLineToolSession(ToolSession):
    """Drop the selected text onto a line, turned to run along it.

    The view feeds this the point under the cursor on whatever line, polyline or
    curve is there, plus that spot's direction; the real text item follows the
    cursor as the preview, so what is on screen is what the click commits.
    """

    wants_line_hover = True

    def __init__(
        self, handle: str, insert: Tuple[float, float], rotation: float, height: float
    ) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_text_on_line_point")
        self.ignore_handle = handle
        self._handle = handle
        self._insert = insert
        self._rotation = rotation
        self._height = height
        self._placement: Optional[Tuple[Tuple[float, float], float]] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def _place(self, point: Tuple[float, float], angle: float) -> Tuple[Tuple[float, float], float]:
        """Where the baseline has to start for the line to run through the text's waist.

        Text sits on its baseline, so an insertion point dropped straight on the line
        would leave the whole label hanging above it; half a cap height along the text's
        own "down" direction puts the line through the middle instead.
        """
        upright = upright_angle(angle)
        radians = math.radians(upright)
        offset = self._height / 2.0
        return (point[0] + math.sin(radians) * offset, point[1] - math.cos(radians) * offset), upright

    def on_click(self, point: Tuple[float, float], angle: Optional[float] = None) -> None:
        if angle is None:
            return
        self._placement = self._place(point, angle)

    def on_text(self, text: str) -> Optional[str]:
        return tr("tool.click_line_first")

    def update_preview(
        self, point: Tuple[float, float], scene: qw.QGraphicsScene, angle: Optional[float] = None
    ) -> None:
        if self._preview_targets is None:
            self._preview_targets = _preview_targets(scene, [self._handle])
        if angle is None:
            _clear_preview_transforms(self._preview_targets)
            return
        target, upright = self._place(point, angle)
        origin = to_scene_point(scene, self._insert)
        destination = to_scene_point(scene, target)
        placement = qg.QTransform()
        placement.translate(destination.x() - origin.x(), destination.y() - origin.y())
        placement.translate(origin.x(), origin.y())
        placement.rotate(upright - self._rotation)
        placement.translate(-origin.x(), -origin.y())
        for item in self._preview_targets:
            item.setTransform(placement)

    def is_done(self) -> bool:
        return self._placement is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._placement is not None
        target, upright = self._placement
        return CompositeCommand(
            [
                MoveCommand(
                    [self._handle],
                    target[0] - self._insert[0],
                    target[1] - self._insert[1],
                ),
                SetTextRotationCommand(self._handle, upright),
            ]
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        _clear_preview_transforms(self._preview_targets)
        self._preview_targets = None
