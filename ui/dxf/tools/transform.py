from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.edit import MoveCommand, RotateCommand, ScaleCommand
from core.dxf_document import DXFDocument
from ui.dxf.items import HANDLE_ROLE
from ui.dxf.tools.base import ToolSession, angle_degrees, parse_coordinate, point_distance, preview_pen
from ui.i18n import tr


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
            scene.addItem(self._preview_item)
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
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            handle_set = set(self._handles)
            self._preview_targets = [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]
            origin = qc.QPointF(*self._base)
            for item in self._preview_targets:
                item.setTransformOriginPoint(origin)
        angle = angle_degrees(self._base, point)
        for item in self._preview_targets:
            item.setRotation(angle)

    def is_done(self) -> bool:
        return self._base is not None and self._angle is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._base is not None and self._angle is not None
        return RotateCommand(self._handles, self._angle, self._base)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        if self._preview_targets is not None:
            for item in self._preview_targets:
                item.setRotation(0)
            self._preview_targets = None


class ScaleToolSession(ToolSession):

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_base_point")
        self._base: Optional[Tuple[float, float]] = None
        self._factor: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_scale_factor")
        else:
            factor = point_distance(self._base, point)
            if factor > 0:
                self._factor = factor

    def on_text(self, text: str) -> Optional[str]:
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_scale_factor")
            return None
        try:
            factor = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.scale_or_point_numeric", value=text)
            factor = point_distance(self._base, coord)
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
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            handle_set = set(self._handles)
            self._preview_targets = [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]
            origin = qc.QPointF(*self._base)
            for item in self._preview_targets:
                item.setTransformOriginPoint(origin)
        factor = point_distance(self._base, point)
        if factor <= 0:
            return
        for item in self._preview_targets:
            item.setScale(factor)

    def is_done(self) -> bool:
        return self._base is not None and self._factor is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._base is not None and self._factor is not None
        return ScaleCommand(self._handles, self._factor, self._base)

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        if self._preview_targets is not None:
            for item in self._preview_targets:
                item.setScale(1.0)
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
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            handle_set = set(self._handles)
            self._preview_targets = [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]
            for item in self._preview_targets:
                item.setTransformOriginPoint(item.boundingRect().center())
        angle = angle_degrees(self._base, point)
        for item in self._preview_targets:
            item.setRotation(angle)

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
        if self._preview_targets is not None:
            for item in self._preview_targets:
                item.setRotation(0)
            self._preview_targets = None


class ScaleEachToolSession(ToolSession):

    def __init__(self, handles: List[str]) -> None:
        super().__init__()
        self._handles = handles
        self.prompt = tr("tool.specify_reference_point")
        self._base: Optional[Tuple[float, float]] = None
        self._factor: Optional[float] = None
        self._preview_item: Optional[qw.QGraphicsLineItem] = None
        self._preview_targets: Optional[List[qw.QGraphicsItem]] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._base is None:
            self._base = point
            self.prompt = tr("tool.specify_scale_factor")
        else:
            factor = point_distance(self._base, point)
            if factor > 0:
                self._factor = factor

    def on_text(self, text: str) -> Optional[str]:
        if self._base is None:
            coord = parse_coordinate(text, last_point=None)
            if coord is None:
                return tr("common.point_xy_format", value=text)
            self._base = coord
            self.prompt = tr("tool.specify_scale_factor")
            return None
        try:
            factor = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=self._base)
            if coord is None:
                return tr("tool.scale_or_point_numeric", value=text)
            factor = point_distance(self._base, coord)
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
            scene.addItem(self._preview_item)
        self._preview_item.setLine(self._base[0], self._base[1], point[0], point[1])

        if self._preview_targets is None:
            handle_set = set(self._handles)
            self._preview_targets = [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]
            for item in self._preview_targets:
                item.setTransformOriginPoint(item.boundingRect().center())
        factor = point_distance(self._base, point)
        if factor <= 0:
            return
        for item in self._preview_targets:
            item.setScale(factor)

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
        if self._preview_targets is not None:
            for item in self._preview_targets:
                item.setScale(1.0)
            self._preview_targets = None

