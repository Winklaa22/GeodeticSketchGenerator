"""A group of commands that behave as one entry in `CommandHistory` — one
Ctrl+Z undoes every sub-command it made. Not called anywhere yet; it's the
foundation the future "geodetic" macro commands (draw points/lines/polylines
for a whole imported point list in one undo step) will build on.
"""
from __future__ import annotations

from typing import Iterable, List

from core.commands.base import Command
from core.dxf_document import DXFDocument


class CompositeCommand:
    def __init__(self, commands: Iterable[Command]) -> None:
        self._commands: List[Command] = list(commands)

    def execute(self, doc: DXFDocument) -> None:
        for command in self._commands:
            command.execute(doc)

    def undo(self, doc: DXFDocument) -> None:
        # Reverse order: later commands may depend on state earlier ones
        # created, so unwind them last-in-first-out.
        for command in reversed(self._commands):
            command.undo(doc)
