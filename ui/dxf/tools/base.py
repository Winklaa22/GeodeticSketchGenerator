from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.dxf_document import DXFDocument
from ui.dxf.items import CONTENT_PIVOT_PROPERTY, CONTENT_ROTATION_PROPERTY
from ui.theme import Color as UiColor


def parse_coordinate(text: str, last_point: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
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


def point_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def angle_degrees(base: Tuple[float, float], point: Tuple[float, float]) -> float:
    return math.degrees(math.atan2(point[1] - base[1], point[0] - base[0]))


def offset_segment_perpendicular(
    start: Tuple[float, float], end: Tuple[float, float], offset: float
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        return start, end
    ux, uy = -dy / length, dx / length
    shift = (ux * offset, uy * offset)
    return (start[0] + shift[0], start[1] + shift[1]), (end[0] + shift[0], end[1] + shift[1])


@dataclass(frozen=True)
class Gizmo:
    """On-canvas grips a tool offers, in DXF/world coordinates.

    The view paints these and decides what counts as a hit; the tool only says where they
    are and what happens when one is dragged.
    """

    center: Tuple[float, float]
    handles: Tuple[Tuple[float, float], ...] = ()
    knob: Optional[Tuple[float, float]] = None

    def points(self) -> Tuple[Tuple[float, float], ...]:
        return self.handles + ((self.knob,) if self.knob is not None else ())


class ToolSession:

    def __init__(self) -> None:
        self.prompt: str = ""

    def gizmo(self) -> Optional[Gizmo]:
        """Grips to draw on the canvas, or None for a tool driven purely by clicks."""
        return None

    def grab(self, point: Tuple[float, float], tolerance: float) -> bool:
        """Try to take hold of a grip near `point`; True means the drag is ours."""
        return False

    def on_click(self, point: Tuple[float, float]) -> None:
        raise NotImplementedError

    def on_text(self, text: str) -> Optional[str]:
        raise NotImplementedError

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        pass

    def is_done(self) -> bool:
        raise NotImplementedError

    def build_command(self, doc: DXFDocument) -> EditCommand:
        raise NotImplementedError

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        pass


def content_rotation(scene: qw.QGraphicsScene) -> Tuple[float, Optional[qc.QPointF]]:
    """The sheet rotation the scene is showing its contents under, if any."""
    rotation = scene.property(CONTENT_ROTATION_PROPERTY)
    pivot = scene.property(CONTENT_PIVOT_PROPERTY)
    if not rotation or pivot is None:
        return 0.0, None
    return float(rotation), pivot


def to_scene_point(scene: qw.QGraphicsScene, point: Tuple[float, float]) -> qc.QPointF:
    """A DXF/world point in scene coordinates.

    Qt applies an item's transform() *after* its rotation(), so a preview transform acts
    on scene coordinates - on a rotated sheet a world-space origin would send the item
    somewhere else for the duration of the gesture.
    """
    rotation, pivot = content_rotation(scene)
    if pivot is None:
        return qc.QPointF(*point)
    radians = math.radians(rotation)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    dx, dy = point[0] - pivot.x(), point[1] - pivot.y()
    return qc.QPointF(pivot.x() + dx * cos_a - dy * sin_a, pivot.y() + dx * sin_a + dy * cos_a)


def add_preview_item(scene: qw.QGraphicsScene, item: qw.QGraphicsItem) -> qw.QGraphicsItem:
    scene.addItem(item)
    rotation = scene.property(CONTENT_ROTATION_PROPERTY)
    pivot = scene.property(CONTENT_PIVOT_PROPERTY)
    if rotation and pivot is not None:
        item.setTransformOriginPoint(pivot)
        item.setRotation(float(rotation))
    return item


def preview_pen() -> qg.QPen:
    pen = qg.QPen(qg.QColor(UiColor.ACCENT))
    pen.setCosmetic(True)
    pen.setStyle(qc.Qt.PenStyle.DashLine)
    return pen
