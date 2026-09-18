from __future__ import annotations

from typing import Optional

from core.detail_view import DetailViewSpec
from core.dxf_document import DXFDocument


class AddDetailViewCommand:

    def __init__(self, spec: DetailViewSpec) -> None:
        self._spec = spec.normalized()
        self.handle: Optional[str] = None

    @property
    def spec(self) -> DetailViewSpec:
        return self._spec

    def execute(self, doc: DXFDocument) -> None:
        if self.handle is not None:
            doc.relink_entity(self.handle)
            return
        self.handle = doc.add_detail_view(self._spec)

    def undo(self, doc: DXFDocument) -> None:
        if self.handle is not None:
            doc.unlink_entity(self.handle)


class UpdateDetailViewCommand:

    def __init__(
        self, handle: str, spec: DetailViewSpec, previous: Optional[DetailViewSpec] = None
    ) -> None:
        self._handle = handle
        self._spec = spec.normalized()
        self._previous = previous.normalized() if previous is not None else None

    @property
    def handle(self) -> str:
        return self._handle

    def execute(self, doc: DXFDocument) -> None:
        if self._previous is None:
            self._previous = doc.detail_view_spec(self._handle)
        doc.set_detail_view_spec(self._handle, self._spec)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_detail_view_spec(self._handle, self._previous)
