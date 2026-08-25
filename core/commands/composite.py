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
        for command in reversed(self._commands):
            command.undo(doc)
