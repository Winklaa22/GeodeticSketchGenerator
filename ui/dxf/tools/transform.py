from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.edit import MoveCommand, RotateCommand, ScaleCommand
from core.dxf_document import DXFDocument
from ui.dxf.items import HANDLE_ROLE
from ui.dxf.tools.base import (
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

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_base_point")
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
        spin = _rotation_about(to_scene_point(scene, self._base), angle_degrees(self._base, point))
        for item in self._preview_targets:
            item.setTransform(spin)

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
    """Scales by a ratio of two picked distances, so a gesture means the same at any zoom.

    Taking the raw distance from the base as the factor made the tool unusable on a
    sheet: there the whole drawing is a few dozen pixels wide, so an ordinary drag is
    tens of drawing units and scaled the selection by that many times.
    """

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_base_point")
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
        # A typed number is still the factor itself - the quickest way to an exact scale.
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
