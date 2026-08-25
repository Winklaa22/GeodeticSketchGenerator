from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.dxf_document import DXFDocument


@runtime_checkable
class Command(Protocol):
    def execute(self, doc: DXFDocument) -> None: ...

    def undo(self, doc: DXFDocument) -> None: ...
