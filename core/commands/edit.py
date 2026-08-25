from __future__ import annotations

from typing import Iterable, List, Sequence

from ezdxf.entities import DXFGraphic

from core.dxf_document import DXFDocument


class DeleteEntityCommand:

    def __init__(self, handles: Iterable[str]) -> None:
        self._handles: List[str] = list(handles)
        self._removed: List[DXFGraphic] = []

    def execute(self, doc: DXFDocument) -> None:
        unlinked = (doc.unlink_entity(handle) for handle in self._handles)
        self._removed = [entity for entity in unlinked if entity is not None]

    def undo(self, doc: DXFDocument) -> None:
        for entity in self._removed:
            doc.restore_entity(entity)
        self._removed = []


class MoveCommand:

    def __init__(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> None:
        self._handles: List[str] = list(handles)
        self._dx = dx
        self._dy = dy
        self._dz = dz

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.translate_entity(handle, self._dx, self._dy, self._dz)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.translate_entity(handle, -self._dx, -self._dy, -self._dz)


class DuplicateEntitiesCommand:

    def __init__(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> None:
        self._handles: List[str] = list(handles)
        self._dx = dx
        self._dy = dy
        self._dz = dz
        self.new_handles: List[str] = []

    def execute(self, doc: DXFDocument) -> None:
        if self.new_handles:
            for handle in self.new_handles:
                doc.relink_entity(handle)
        else:
            self.new_handles = [
                doc.duplicate_entity(handle, self._dx, self._dy, self._dz) for handle in self._handles
            ]

    def undo(self, doc: DXFDocument) -> None:
        for handle in self.new_handles:
            doc.unlink_entity(handle)


class RotateCommand:

    def __init__(self, handles: Iterable[str], angle: float, center: Sequence[float]) -> None:
        self._handles: List[str] = list(handles)
        self._angle = angle
        self._center = center

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.rotate_entity(handle, self._angle, self._center)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.rotate_entity(handle, -self._angle, self._center)


class ScaleCommand:

    def __init__(self, handles: Iterable[str], factor: float, center: Sequence[float]) -> None:
        self._handles: List[str] = list(handles)
        self._factor = factor
        self._center = center

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.scale_entity(handle, self._factor, self._center)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.scale_entity(handle, 1.0 / self._factor, self._center)
