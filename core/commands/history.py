from __future__ import annotations

from typing import List

from core.commands.base import Command
from core.dxf_document import DXFDocument

DEFAULT_MAX_DEPTH = 200


class CommandHistory:
    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self._max_depth = max_depth
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []

    def execute(self, command: Command, doc: DXFDocument) -> None:
        command.execute(doc)
        self._undo_stack.append(command)
        if len(self._undo_stack) > self._max_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self, doc: DXFDocument) -> bool:
        if not self._undo_stack:
            return False
        command = self._undo_stack.pop()
        command.undo(doc)
        self._redo_stack.append(command)
        return True

    def redo(self, doc: DXFDocument) -> bool:
        if not self._redo_stack:
            return False
        command = self._redo_stack.pop()
        command.execute(doc)
        self._undo_stack.append(command)
        return True

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
