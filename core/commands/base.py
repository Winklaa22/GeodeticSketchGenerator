"""The Command protocol every DXF edit command implements.

A command never touches ezdxf directly — it only calls methods on the
`DXFDocument` passed into `execute`/`undo`, so `CommandHistory` can replay or
reverse any command without knowing what it does.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.dxf_document import DXFDocument


@runtime_checkable
class Command(Protocol):
    def execute(self, doc: DXFDocument) -> None: ...

    def undo(self, doc: DXFDocument) -> None: ...
