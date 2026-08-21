"""Drawing commands — section 1 of the DXF edit command spec (point, line,
circle, text, 2D/3D polyline; move/rectangle are later phases).

Every command follows the same shape: `execute` asks the `DXFDocument` to
create the entity and remembers its handle; `undo` unlinks that handle
(see `DXFDocument.unlink_entity` — the entity survives in the entity
database, so a `redo` that calls `execute` again just creates a fresh one).
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from core.dxf_document import DXFDocument

DEFAULT_LAYER = "0"


class AddPointCommand:
    def __init__(self, location: Sequence[float], layer: str = DEFAULT_LAYER) -> None:
        self._location = location
        self._layer = layer
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
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
    ) -> None:
        self._text = text
        self._insert = insert
        self._height = height
        self._layer = layer
        self._rotation = rotation
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        self._handle = doc.add_text(self._text, self._insert, self._height, self._layer, self._rotation)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)

    @property
    def handle(self) -> Optional[str]:
        """The created entity's handle, once executed — lets the Text tool
        select what it just placed (see DxfViewer._finish_tool)."""
        return self._handle


class AddPolyline2DCommand:
    def __init__(self, points: Iterable[Sequence[float]], layer: str = DEFAULT_LAYER, closed: bool = False) -> None:
        self._points: List[Sequence[float]] = list(points)
        self._layer = layer
        self._closed = closed
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
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
        self._handle = doc.add_polyline3d(self._points, self._layer, self._closed)

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)
