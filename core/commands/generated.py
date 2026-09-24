from __future__ import annotations

from typing import Iterable, List, Optional

from core.commands.base import Command
from core.dxf_document import DXFDocument
from ezdxf.entities import DXFGraphic


class MarkGeneratedCommand:
    """Runs a draw command and stamps whatever it produced with the mode behind it.

    Which entities those are is taken from what appeared in the modelspace, so no
    draw command has to report its own handles - and a redo, which relinks the very
    same entities, simply stamps them again.
    """

    def __init__(self, mode: str, command: Command) -> None:
        self._mode = mode
        self._command = command

    def execute(self, doc: DXFDocument) -> None:
        before = {entity.dxf.handle for entity in doc.modelspace}
        self._command.execute(doc)
        for entity in doc.modelspace:
            if entity.dxf.handle not in before:
                doc.mark_generated(entity.dxf.handle, self._mode)

    def undo(self, doc: DXFDocument) -> None:
        self._command.undo(doc)


class DeleteGeneratedCommand:
    """Clears what an earlier run drew for `modes`, leaving every other entity alone.

    Which entities those are can only be known once the command runs, since it is the
    drawing that carries the stamps - but the answer is kept from then on, so undoing
    and redoing puts back and takes away that same set rather than a fresh guess.
    """

    def __init__(self, modes: Iterable[str]) -> None:
        self._modes = list(modes)
        self._handles: Optional[List[str]] = None
        self._removed: List[DXFGraphic] = []

    def execute(self, doc: DXFDocument) -> None:
        if self._handles is None:
            self._handles = doc.generated_handles(self._modes)
        unlinked = (doc.unlink_entity(handle) for handle in self._handles)
        self._removed = [entity for entity in unlinked if entity is not None]

    def undo(self, doc: DXFDocument) -> None:
        for entity in self._removed:
            doc.restore_entity(entity)
        self._removed = []
