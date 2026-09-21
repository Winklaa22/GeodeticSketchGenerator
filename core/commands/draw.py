from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from core.dxf_document import DXFDocument
from core.fonts import DEFAULT_FONT_ID

DEFAULT_LAYER = "0"


class AddPointCommand:
    def __init__(self, location: Sequence[float], layer: str = DEFAULT_LAYER) -> None:
        self._location = location
        self._layer = layer
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_point(self._location, self._layer)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)


class AddLineCommand:
    def __init__(self, start: Sequence[float], end: Sequence[float], layer: str = DEFAULT_LAYER) -> None:
        self._start = start
        self._end = end
        self._layer = layer
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_line(self._start, self._end, self._layer)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)


class AddCircleCommand:
    def __init__(self, center: Sequence[float], radius: float, layer: str = DEFAULT_LAYER) -> None:
        self._center = center
        self._radius = radius
        self._layer = layer
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_circle(self._center, self._radius, self._layer)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)


class AddTextCommand:
    def __init__(
        self,
        text: str,
        insert: Sequence[float],
        height: float,
        layer: str = DEFAULT_LAYER,
        rotation: float = 0.0,
        halign: str = "left",
        valign: str = "bottom",
        font_id: str = DEFAULT_FONT_ID,
        italic: bool = False,
        lineweight_mm: Optional[float] = None,
    ) -> None:
        self._text = text
        self._insert = insert
        self._height = height
        self._layer = layer
        self._rotation = rotation
        self._halign = halign
        self._valign = valign
        self._font_id = font_id
        self._italic = italic
        self._lineweight_mm = lineweight_mm
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_text(
                self._text,
                self._insert,
                self._height,
                self._layer,
                self._rotation,
                self._halign,
                self._valign,
                self._font_id,
                self._italic,
                self._lineweight_mm,
            )

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)

    @property
    def handle(self) -> Optional[str]:
        return self._handle


class AddPolyline2DCommand:
    def __init__(self, points: Iterable[Sequence[float]], layer: str = DEFAULT_LAYER, closed: bool = False) -> None:
        self._points: List[Sequence[float]] = list(points)
        self._layer = layer
        self._closed = closed
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_lwpolyline(self._points, self._layer, self._closed)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)


class AddPolyline3DCommand:
    def __init__(self, points: Iterable[Sequence[float]], layer: str = DEFAULT_LAYER, closed: bool = False) -> None:
        self._points: List[Sequence[float]] = list(points)
        self._layer = layer
        self._closed = closed
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
        else:
            self._handle = doc.add_polyline3d(self._points, self._layer, self._closed)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)
